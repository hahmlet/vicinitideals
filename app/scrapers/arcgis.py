"""Gresham ArcGIS REST helpers for parcel lookup."""

from __future__ import annotations

import re
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any, Literal

import httpx

from app.config import settings
from app.utils.proxy_pool import gis_proxy


class ArcGISLookupError(RuntimeError):
    """Raised when the Gresham ArcGIS REST API cannot be queried successfully."""


LEGACY_TAXLOTS_URL = "https://gis.greshamoregon.gov/ext/rest/services/Taxlots/MapServer/0/query"
LEGACY_OUT_FIELDS = (
    "RNO,STATEID,SITEADDR,OWNER1,OWNERADDR,OWNERCITY,OWNERSTATE,OWNERZIP,"
    "LANDVAL,BLDGVAL,TOTALVAL,BLDGSQFT,YEARBUILT,TAXCODE,GIS_ACRES,SQFT,LEGAL,ZONE,LANDUSE"
)


@dataclass(slots=True)
class GreshamParcelMatch:
    state_id: str | None = None
    rno: str | None = None
    site_address: str | None = None
    owner_name: str | None = None
    owner_street: str | None = None
    owner_city: str | None = None
    owner_state: str | None = None
    owner_zip: str | None = None
    land_value: Decimal | None = None
    building_value: Decimal | None = None
    total_value: Decimal | None = None
    building_sqft: Decimal | None = None
    year_built: int | None = None
    tax_code: str | None = None
    gis_acres: Decimal | None = None
    sqft: Decimal | None = None
    legal_description: str | None = None
    zone: str | None = None
    land_use: str | None = None
    geometry: dict[str, Any] | None = None


@dataclass(slots=True)
class GreshamLookupResult:
    input_address: str
    match_status: Literal["single_match", "multiple_matches", "no_match"]
    parcels: list[GreshamParcelMatch] = field(default_factory=list)


async def lookup_gresham_parcels(
    queries: list[str] | None = None,
    *,
    apn: str | None = None,
    address: str | None = None,
) -> list[Any]:
    """Fetch parcel details from Gresham ArcGIS, supporting the REAL-65 batch contract."""
    if queries is not None:
        return await _lookup_gresham_batch(queries)
    return await _lookup_gresham_live_parcels(apn=apn, address=address)


async def lookup_gresham_candidates(
    *,
    apn: str | None = None,
    address: str | None = None,
) -> list[dict[str, Any]]:
    """Compatibility helper for project attachment flows that still resolve one parcel at a time."""
    return await _lookup_gresham_live_parcels(apn=apn, address=address)


async def _lookup_gresham_live_parcels(
    *,
    apn: str | None = None,
    address: str | None = None,
) -> list[dict[str, Any]]:
    """Fetch parcel details from the confirmed Gresham Taxlots endpoint."""
    apn_value = (apn or "").strip().upper()
    apn_compact = re.sub(r"[^A-Z0-9]", "", apn_value)
    address_value = " ".join((address or "").split()).upper()
    if not apn_value and not address_value:
        return []

    timeout = httpx.Timeout(settings.gresham_arcgis_timeout_seconds)

    try:
        async with httpx.AsyncClient(timeout=timeout, proxy=gis_proxy()) as client:
            features: list[dict[str, Any]] = []
            if apn_value:
                # Gresham stores our canonical "APN" as STATEID (e.g. "1S3E10AD 05800"),
                # NOT RNO (RNO is the R-prefixed tax-account number like "R993105510").
                # Our DB may hold the APN in several formats — "1S3E10AD  -05800",
                # "1S3E10AD-05800", or the bare compact form — so match against a set
                # of the common variants.
                variants = {
                    apn_value,
                    apn_compact,
                    apn_compact.replace(" ", ""),
                }
                if len(apn_compact) > 8 and apn_compact[:8].isalnum():
                    # Reconstruct "1S3E10AD 05800" and "1S3E10AD-05800" from the compact form.
                    head, tail = apn_compact[:8], apn_compact[8:]
                    variants.add(f"{head} {tail}")
                    variants.add(f"{head}-{tail}")
                variant_list = ", ".join(f"'{_escape_sql(v)}'" for v in variants if v)
                features = await _query_legacy_taxlots(
                    client,
                    f"UPPER(STATEID) IN ({variant_list})",
                )
            elif address_value:
                features = await _query_legacy_taxlots(
                    client,
                    f"SITEADDR = '{_escape_sql(address_value)}'",
                )
                if not features:
                    features = await _query_legacy_taxlots(
                        client,
                        f"UPPER(SITEADDR) LIKE '%{_escape_sql(address_value)}%'",
                    )
    except httpx.HTTPError as exc:
        raise ArcGISLookupError(f"ArcGIS REST request failed: {exc}") from exc

    parcels: list[dict[str, Any]] = []
    seen_apns: set[str] = set()
    for feature in features:
        parcel = _feature_to_parcel(feature)
        apn_key = str(parcel.get("apn") or "").strip().upper()
        if not apn_key or apn_key in seen_apns:
            continue
        seen_apns.add(apn_key)
        parcels.append(parcel)
    return parcels


async def _lookup_gresham_batch(queries: list[str]) -> list[GreshamLookupResult]:
    timeout = httpx.Timeout(settings.gresham_arcgis_timeout_seconds)
    normalized_queries = [" ".join(str(query or "").split()).upper() for query in queries]

    try:
        async with httpx.AsyncClient(timeout=timeout, proxy=gis_proxy()) as client:
            results: list[GreshamLookupResult] = []
            for query in normalized_queries:
                if not query:
                    results.append(GreshamLookupResult(input_address="", match_status="no_match", parcels=[]))
                    continue

                features = await _query_legacy_taxlots(client, f"SITEADDR = '{_escape_sql(query)}'")
                if not features:
                    features = await _query_legacy_taxlots(
                        client,
                        f"UPPER(SITEADDR) LIKE '%{_escape_sql(query)}%'",
                    )

                match_status: Literal["single_match", "multiple_matches", "no_match"]
                if not features:
                    match_status = "no_match"
                elif len(features) == 1:
                    match_status = "single_match"
                else:
                    match_status = "multiple_matches"

                results.append(
                    GreshamLookupResult(
                        input_address=query,
                        match_status=match_status,
                        parcels=[_legacy_feature_to_parcel(feature) for feature in features],
                    )
                )
    except httpx.HTTPError as exc:
        raise ArcGISLookupError(f"ArcGIS REST request failed: {exc}") from exc

    return results


async def _query_legacy_taxlots(
    client: httpx.AsyncClient,
    where: str,
) -> list[dict[str, Any]]:
    response = await client.get(
        LEGACY_TAXLOTS_URL,
        params={
            "where": where,
            "outFields": LEGACY_OUT_FIELDS,
            "returnGeometry": "true",
            "outSR": 4326,
            "f": "pjson",
        },
    )
    response.raise_for_status()
    payload = response.json()
    _raise_if_arcgis_error(payload)
    return [feature for feature in payload.get("features", []) if isinstance(feature, dict)]


def _legacy_feature_to_parcel(feature: dict[str, Any]) -> GreshamParcelMatch:
    attributes = feature.get("attributes") or {}
    owner_name = " ".join(
        str(item).strip()
        for item in (attributes.get("OWNER1"), attributes.get("OWNER2"), attributes.get("OWNER3"))
        if item not in (None, "") and str(item).strip()
    ) or None
    return GreshamParcelMatch(
        state_id=_to_string(attributes.get("STATEID")),
        rno=_to_string(attributes.get("RNO")),
        site_address=_to_string(attributes.get("SITEADDR")),
        owner_name=owner_name,
        owner_street=_to_string(attributes.get("OWNERADDR")),
        owner_city=_to_string(attributes.get("OWNERCITY")),
        owner_state=_to_string(attributes.get("OWNERSTATE")),
        owner_zip=_to_string(attributes.get("OWNERZIP")),
        land_value=_to_decimal(attributes.get("LANDVAL")),
        building_value=_to_decimal(attributes.get("BLDGVAL")),
        total_value=_to_decimal(attributes.get("TOTALVAL")),
        building_sqft=_to_decimal(attributes.get("BLDGSQFT")),
        year_built=_to_int(attributes.get("YEARBUILT")),
        tax_code=_to_string(attributes.get("TAXCODE")),
        gis_acres=_to_decimal(attributes.get("GIS_ACRES")),
        sqft=_to_decimal(attributes.get("SQFT")),
        legal_description=_to_string(attributes.get("LEGAL")),
        zone=_to_string(attributes.get("ZONE")),
        land_use=_to_string(attributes.get("LANDUSE")),
        geometry=feature.get("geometry") if isinstance(feature.get("geometry"), dict) else None,
    )


async def _query_address_candidates(
    client: httpx.AsyncClient,
    *,
    base_url: str,
    address: str,
) -> list[str]:
    layer_url = f"{base_url}/{settings.gresham_arcgis_address_layer_id}/query"
    escaped_address = _escape_sql(address.upper())
    where = f"UPPER(FULLADDR) LIKE '%{escaped_address}%'"

    response = await client.get(
        layer_url,
        params={
            "where": where,
            "outFields": "RNO,FULLADDR,CITY,STATE,ZIPCODE",
            "returnGeometry": "false",
            "f": "pjson",
        },
    )
    response.raise_for_status()
    payload = response.json()
    _raise_if_arcgis_error(payload)
    return [
        str((feature.get("attributes") or {}).get("RNO") or "").strip().upper()
        for feature in payload.get("features", [])
        if (feature.get("attributes") or {}).get("RNO")
    ]


async def _query_tax_lots(
    client: httpx.AsyncClient,
    *,
    base_url: str,
    where: str,
) -> list[dict[str, Any]]:
    layer_url = f"{base_url}/{settings.gresham_arcgis_taxlot_layer_id}/query"
    response = await client.get(
        layer_url,
        params={
            "where": where,
            "outFields": "*",
            "returnGeometry": "true",
            "f": "pjson",
        },
    )
    response.raise_for_status()
    payload = response.json()
    _raise_if_arcgis_error(payload)
    return list(payload.get("features", []))


def _raise_if_arcgis_error(payload: dict[str, Any]) -> None:
    error = payload.get("error")
    if not isinstance(error, dict):
        return
    message = error.get("message") or "ArcGIS REST query failed"
    details = error.get("details") or []
    detail_text = f" ({'; '.join(str(item) for item in details if item)})" if details else ""
    raise ArcGISLookupError(f"{message}{detail_text}")


def _build_taxlot_address_where(address: str) -> str:
    normalized = " ".join(address.upper().split())
    escaped = _escape_sql(normalized)
    parts = normalized.split()
    if parts and parts[0].isdigit():
        street_num = _escape_sql(parts[0])
        street_name = _escape_sql(" ".join(parts[1:]))
        return (
            f"(SITESTRNO = {street_num} AND UPPER(SITEADDR) LIKE '%{street_name}%') "
            f"OR UPPER(SITEADDR) LIKE '%{escaped}%'"
        )
    return f"UPPER(SITEADDR) LIKE '%{escaped}%'"


def _feature_to_parcel(feature: dict[str, Any]) -> dict[str, Any]:
    attributes = feature.get("attributes") or {}
    address = _first_non_empty(
        _compose_site_address(attributes),
        attributes.get("FULLADDR"),
        attributes.get("SITEADDR"),
    )
    owner_name = " ".join(
        str(item).strip()
        for item in (attributes.get("OWNER1"), attributes.get("OWNER2"), attributes.get("OWNER3"))
        if item not in (None, "") and str(item).strip()
    ) or None
    owner_street = _to_string(attributes.get("OWNERADDR"))
    owner_city = _to_string(attributes.get("OWNERCITY"))
    owner_state = _to_string(attributes.get("OWNERSTATE"))
    owner_zip = _to_string(attributes.get("OWNERZIP"))
    owner_mailing = ", ".join(
        piece for piece in [owner_street, owner_city, owner_state, owner_zip] if piece
    ) or None

    # Gresham's canonical parcel identifier is STATEID (state map-township-range,
    # e.g. "1S3E10AD 05800"), not RNO (the R-prefixed tax-account number). Keep the
    # Parcel.apn aligned to STATEID so we match existing rows seeded from RLIS.
    stateid = _to_string(attributes.get("STATEID"))
    rno = _to_string(attributes.get("RNO"))
    return {
        "apn": (stateid or rno or "").strip().upper(),
        "state_id": stateid,
        "address_normalized": address,
        "address_raw": address,
        "owner_name": owner_name,
        "owner_mailing_address": owner_mailing,
        "owner_street": owner_street,
        "owner_city": owner_city,
        "owner_state": owner_state,
        "owner_zip": owner_zip,
        "lot_sqft": _to_decimal(attributes.get("SQFT")),
        "gis_acres": _to_decimal(attributes.get("GIS_ACRES")),
        "zoning_code": _to_string(attributes.get("ZONE")),
        "zoning_description": _to_string(attributes.get("ZONE")),
        "current_use": _to_string(attributes.get("LANDUSE")) or _to_string(attributes.get("PROP_CODE")),
        "assessed_value_land": _to_decimal(attributes.get("LANDVAL")),
        "assessed_value_improvements": _to_decimal(attributes.get("BLDGVAL")),
        "total_assessed_value": _to_decimal(attributes.get("TOTALVAL")),
        "tax_code": _to_string(attributes.get("TAXCODE")),
        "legal_description": _to_string(attributes.get("LEGAL")),
        "year_built": _to_int(attributes.get("YEARBUILT")),
        "building_sqft": _to_decimal(attributes.get("BLDGSQFT")),
        "unit_count": _to_int(attributes.get("UNITS")),
        "geometry": feature.get("geometry"),
    }


def _compose_site_address(attributes: dict[str, Any]) -> str | None:
    parts = [
        attributes.get("SITESTRNO"),
        attributes.get("SITEADDR"),
        attributes.get("SITECITY"),
        "OR" if attributes.get("SITECITY") else None,
        attributes.get("SITEZIP"),
    ]
    value = " ".join(str(part).strip() for part in parts if part not in (None, "") and str(part).strip())
    return value or None


def _first_non_empty(*values: Any) -> str | None:
    for value in values:
        if value not in (None, "") and str(value).strip():
            return str(value).strip()
    return None


def _escape_sql(value: str) -> str:
    return value.replace("'", "''")


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


async def iter_all_gresham_taxlots(
    *,
    page_size: int = 1000,
    timeout_seconds: float | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """Yield every Gresham taxlot feature as a ready-to-upsert parcel dict.

    Paginates the legacy Taxlots endpoint via resultOffset/resultRecordCount
    ordered by OBJECTID for stability. Each yielded dict matches the shape
    produced by `_feature_to_parcel` (i.e. Parcel column names) so callers can
    hand it straight to `_upsert_parcel`.
    """
    timeout = httpx.Timeout(timeout_seconds or max(settings.gresham_arcgis_timeout_seconds, 60.0))

    offset = 0
    async with httpx.AsyncClient(timeout=timeout, proxy=gis_proxy()) as client:
        while True:
            response = await client.get(
                LEGACY_TAXLOTS_URL,
                params={
                    "where": "1=1",
                    "outFields": LEGACY_OUT_FIELDS,
                    "returnGeometry": "true",
                    "outSR": 4326,
                    "orderByFields": "OBJECTID",
                    "resultOffset": offset,
                    "resultRecordCount": page_size,
                    "f": "pjson",
                },
            )
            response.raise_for_status()
            payload = response.json()
            _raise_if_arcgis_error(payload)
            features = [f for f in payload.get("features", []) if isinstance(f, dict)]
            if not features:
                return
            for feature in features:
                yield _feature_to_parcel(feature)
            if len(features) < page_size or not payload.get("exceededTransferLimit", False):
                # Last page: either short page or the server indicates no overflow.
                if len(features) < page_size:
                    return
            offset += len(features)


__all__ = [
    "ArcGISLookupError",
    "iter_all_gresham_taxlots",
    "lookup_gresham_candidates",
    "lookup_gresham_parcels",
]
