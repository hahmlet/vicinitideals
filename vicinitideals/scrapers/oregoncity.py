"""Oregon City exact-address lookup helpers via public ArcGIS REST services."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any, Literal

import httpx

from vicinitideals.config import settings
from vicinitideals.schemas.parcel import OregonCityParcelResult
from vicinitideals.utils.proxy_pool import gis_proxy


class OregonCityLookupError(RuntimeError):
    """Raised when a required Oregon City ArcGIS call fails."""


async def lookup_oregoncity_parcel(address: str) -> OregonCityParcelResult:
    """Exact-address lookup for Oregon City parcel, zoning, and UGB facts."""
    normalized_address = " ".join(address.split()).upper()
    if not normalized_address:
        raise OregonCityLookupError("Address is required for Oregon City lookup")

    timeout = httpx.Timeout(settings.oregoncity_arcgis_timeout_seconds)
    try:
        async with httpx.AsyncClient(timeout=timeout, proxy=gis_proxy()) as client:
            address_feature = await _query_address_feature(client, normalized_address)
            if address_feature is None:
                return OregonCityParcelResult(
                    input_address=normalized_address,
                    match_status="no_match",
                )

            geometry = address_feature.get("geometry") or {}
            x = geometry.get("x")
            y = geometry.get("y")
            if x in (None, "") or y in (None, ""):
                raise OregonCityLookupError("Address lookup did not return a usable SR 2913 point")

            taxlot_feature = await _query_taxlot_feature(client, x=x, y=y)
            if taxlot_feature is None:
                return OregonCityParcelResult(
                    input_address=normalized_address,
                    match_status="no_match",
                )

            result = _feature_to_result(normalized_address, taxlot_feature, address_feature)
            try:
                result.flood_hazard = await _lookup_flood_hazard(client, x=x, y=y)
            except OregonCityLookupError:
                result.flood_hazard = None
            return result
    except httpx.HTTPError as exc:
        raise OregonCityLookupError(f"ArcGIS request failed: {exc}") from exc


async def _query_address_feature(
    client: httpx.AsyncClient,
    address: str,
) -> dict[str, Any] | None:
    where_clauses = [
        f"UPPER(ADDRESS_Pts.SITUS) = '{_escape_sql(address)}'",
        f"UPPER(ADDRESS_Pts.SITUS) LIKE '%{_escape_sql(address)}%'",
    ]

    for where in where_clauses:
        response = await client.get(
            settings.oregoncity_arcgis_address_url,
            params={
                "where": where,
                "outFields": "ADDRESS_Pts.SITUS,ADDRESS_Pts.CITY,ADDRESS_Pts.ZIP5",
                "returnGeometry": "true",
                "f": "pjson",
            },
        )
        response.raise_for_status()
        payload = response.json()
        _raise_if_arcgis_error(payload)
        features = [item for item in payload.get("features", []) if isinstance(item, dict)]
        if features:
            return features[0]
    return None


async def _query_taxlot_feature(
    client: httpx.AsyncClient,
    *,
    x: Any,
    y: Any,
) -> dict[str, Any] | None:
    response = await client.get(
        settings.oregoncity_arcgis_taxlot_url,
        params={
            "geometry": f"{x},{y}",
            "geometryType": "esriGeometryPoint",
            "inSR": 2913,
            "spatialRel": "esriSpatialRelIntersects",
            "outFields": (
                "APN,PARCEL_NUMBER,SITUS_FULL_ADDRESS,GIS_ACRES,ZONING,"
                "COMPREHENSIVE_PLAN,TAXLOT_IN_CITY,TAXLOT_IN_UGB,YEARBLT,"
                "LIVING_AREA,TOTALVAL,SALE_PRICE,DOC_DATE"
            ),
            "returnGeometry": "false",
            "f": "pjson",
        },
    )
    response.raise_for_status()
    payload = response.json()
    _raise_if_arcgis_error(payload)
    features = [item for item in payload.get("features", []) if isinstance(item, dict)]
    return features[0] if features else None


async def _lookup_flood_hazard(
    client: httpx.AsyncClient,
    *,
    x: Any,
    y: Any,
) -> str | None:
    try:
        for layer_id in (3, 4):
            response = await client.get(
                f"https://maps.orcity.org/arcgis/rest/services/HazardsAndFloodInfo_PUBLIC/MapServer/{layer_id}/query",
                params={
                    "geometry": f"{x},{y}",
                    "geometryType": "esriGeometryPoint",
                    "inSR": 2913,
                    "spatialRel": "esriSpatialRelIntersects",
                    "outFields": "FLD_ZONE",
                    "returnGeometry": "false",
                    "f": "pjson",
                },
            )
            response.raise_for_status()
            payload = response.json()
            _raise_if_arcgis_error(payload)
            features = [item for item in payload.get("features", []) if isinstance(item, dict)]
            if not features:
                continue
            attributes = features[0].get("attributes") or {}
            zone = _to_string(attributes.get("FLD_ZONE"))
            if zone:
                return zone
            return "flood_overlay"
    except httpx.HTTPError as exc:
        raise OregonCityLookupError(f"Optional flood lookup failed: {exc}") from exc
    return None


def _feature_to_result(
    input_address: str,
    feature: dict[str, Any],
    address_feature: dict[str, Any],
) -> OregonCityParcelResult:
    attributes = feature.get("attributes") or {}
    address_attributes = address_feature.get("attributes") or {}
    return OregonCityParcelResult(
        input_address=input_address,
        match_status="single_match",
        situs_address=_first_non_empty(
            attributes.get("SITUS_FULL_ADDRESS"),
            address_attributes.get("ADDRESS_Pts.SITUS"),
        ),
        apn=_to_string(attributes.get("APN")),
        parcel_number=_to_string(attributes.get("PARCEL_NUMBER")),
        zoning_code=_to_string(attributes.get("ZONING")),
        comp_plan=_to_string(attributes.get("COMPREHENSIVE_PLAN")),
        in_city=_yes_no_to_bool(attributes.get("TAXLOT_IN_CITY")),
        ugb_status=_ugb_status(attributes.get("TAXLOT_IN_UGB")),
        gis_acres=_to_decimal(attributes.get("GIS_ACRES")),
        year_built=_to_int(attributes.get("YEARBLT")),
        living_area_sqft=_to_decimal(attributes.get("LIVING_AREA")),
        total_assessed_value=_to_decimal(attributes.get("TOTALVAL")),
        sale_price=_to_decimal(attributes.get("SALE_PRICE")),
        sale_date=_to_string(attributes.get("DOC_DATE")),
    )


def _raise_if_arcgis_error(payload: dict[str, Any]) -> None:
    error = payload.get("error")
    if not isinstance(error, dict):
        return
    message = error.get("message") or "ArcGIS REST query failed"
    details = error.get("details") or []
    detail_text = f" ({'; '.join(str(item) for item in details if item)})" if details else ""
    raise OregonCityLookupError(f"{message}{detail_text}")


def _escape_sql(value: str) -> str:
    return value.replace("'", "''")


def _yes_no_to_bool(value: Any) -> bool | None:
    normalized = _to_string(value)
    if normalized is None:
        return None
    normalized = normalized.upper()
    if normalized == "Y":
        return True
    if normalized == "N":
        return False
    return None


def _ugb_status(value: Any) -> Literal["inside", "outside"] | None:
    normalized = _to_string(value)
    if normalized is None:
        return None
    normalized = normalized.upper()
    if normalized == "Y":
        return "inside"
    if normalized == "N":
        return "outside"
    return None


def _first_non_empty(*values: Any) -> str | None:
    for value in values:
        text = _to_string(value)
        if text:
            return text
    return None


def _to_decimal(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _to_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(str(value))
    except ValueError:
        return None


def _to_string(value: Any) -> str | None:
    if value in (None, ""):
        return None
    text = str(value).strip()
    return text or None


__all__ = ["OregonCityLookupError", "lookup_oregoncity_parcel"]
