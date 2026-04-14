"""Portland exact-address property lookup via public ArcGIS REST services."""

from __future__ import annotations

import asyncio
import math
import re
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx

from app.config import settings
from app.utils.proxy_pool import gis_proxy
from app.schemas.parcel import (
    PortlandBuildingDetails,
    PortlandCoordinates,
    PortlandHazardFlags,
    PortlandLotMetrics,
    PortlandMailingAddress,
    PortlandParcelIds,
    PortlandParcelResult,
    PortlandValuation,
    PortlandZoningContext,
)


class PortlandMapsLookupError(RuntimeError):
    """Raised when a required Portland ArcGIS REST request fails."""


async def lookup_portland_parcel(address: str) -> PortlandParcelResult:
    """Resolve one Portland address into parcel, zoning, planning, and hazard context."""
    normalized_address = " ".join(address.split()).upper()
    if not normalized_address:
        raise PortlandMapsLookupError("Address is required for Portland lookup")

    base_url = settings.portlandmaps_base_url.rstrip("/")
    timeout = httpx.Timeout(settings.portlandmaps_timeout_seconds)

    try:
        async with httpx.AsyncClient(timeout=timeout, proxy=gis_proxy()) as client:
            geocode_payload = await _get_json(
                client,
                f"{base_url}/Public/Address_Geocoding_PDX/GeocodeServer/findAddressCandidates",
                params={
                    "SingleLine": normalized_address,
                    "maxLocations": 5,
                    "outFields": "*",
                    "f": "pjson",
                },
            )
            candidates = [item for item in geocode_payload.get("candidates", []) if isinstance(item, dict)]
            selected_candidate, is_ambiguous = _select_candidate(candidates, normalized_address)
            if is_ambiguous:
                return PortlandParcelResult(input_address=normalized_address, match_status="ambiguous")
            if selected_candidate is None:
                return PortlandParcelResult(input_address=normalized_address, match_status="no_match")

            candidate_attrs = _feature_attributes(selected_candidate)
            match_address = _first_non_empty(
                selected_candidate.get("address"),
                candidate_attrs.get("Match_addr"),
                candidate_attrs.get("LongLabel"),
                candidate_attrs.get("ShortLabel"),
            )
            raw_x = _to_float(_first_non_empty((selected_candidate.get("location") or {}).get("x"), candidate_attrs.get("X")))
            raw_y = _to_float(_first_non_empty((selected_candidate.get("location") or {}).get("y"), candidate_attrs.get("Y")))
            latitude, longitude = _coerce_lat_lon(raw_x, raw_y)

            address_id = _string(candidate_attrs.get("ADDRESS_ID"))
            state_id = _normalize_state_id(candidate_attrs.get("STATE_ID"))
            property_id = _string(candidate_attrs.get("PROPERTY_ID"))
            tlid = None

            linkage_feature = await _safe_query_address_linkage(
                client,
                base_url=base_url,
                matched_address=match_address,
                raw_x=raw_x,
                raw_y=raw_y,
            )
            linkage_attrs = _feature_attributes(linkage_feature)
            address_id = _first_non_empty(address_id, linkage_attrs.get("ADDRESS_ID"))
            state_id = _normalize_state_id(_first_non_empty(state_id, linkage_attrs.get("STATE_ID")))
            property_id = _first_non_empty(property_id, linkage_attrs.get("PROPERTY_ID"), linkage_attrs.get("PROPERTYID"))
            tlid = _first_non_empty(linkage_attrs.get("TLID"), candidate_attrs.get("TLID"))

            taxlot_feature = await _query_taxlot_feature(
                client,
                base_url=base_url,
                state_id=state_id,
                property_id=property_id,
                tlid=tlid,
                raw_x=raw_x,
                raw_y=raw_y,
            )
            taxlot_attrs = _feature_attributes(taxlot_feature)

            zoning_features, overlay_features, bds_features, building_features = await asyncio.gather(
                _safe_query_point_features(client, f"{base_url}/Public/Zoning/MapServer/0/query", raw_x=raw_x, raw_y=raw_y),
                _safe_query_point_features(client, f"{base_url}/Public/Zoning/MapServer/3/query", raw_x=raw_x, raw_y=raw_y),
                _safe_query_point_features(client, f"{base_url}/Public/BDS_Property/FeatureServer/0/query", raw_x=raw_x, raw_y=raw_y),
                _safe_query_point_features(client, f"{base_url}/COP_OpenData_Property/MapServer/184/query", raw_x=raw_x, raw_y=raw_y),
            )
            if not building_features:
                building_features = await _safe_query_point_features(
                    client,
                    f"{base_url}/COP_OpenData_Property/MapServer/48/query",
                    raw_x=raw_x,
                    raw_y=raw_y,
                )

            zoning_feature = _select_best_feature(
                zoning_features,
                state_id=state_id,
                address_id=address_id,
                property_id=property_id,
                matched_address=match_address,
            )
            bds_feature = _select_best_feature(
                bds_features,
                state_id=state_id,
                address_id=address_id,
                property_id=property_id,
                matched_address=match_address,
            )
            building_feature = _select_best_feature(
                building_features,
                state_id=state_id,
                address_id=address_id,
                property_id=property_id,
                matched_address=match_address,
            )

            bds_attrs = _feature_attributes(bds_feature)
            building_attrs = _feature_attributes(building_feature)

            land_value = _first_decimal(
                taxlot_attrs,
                "LANDVAL",
                "LANDVAL3",
                "LANDVAL2",
                "LANDVAL1",
            )
            improvements_value = _first_decimal(
                taxlot_attrs,
                "BLDGVAL",
                "BLDGVAL3",
                "BLDGVAL2",
                "BLDGVAL1",
            )
            total_value = _best_total_value(taxlot_attrs, land_value, improvements_value)

            return PortlandParcelResult(
                input_address=normalized_address,
                match_status="single_match",
                address_match=match_address,
                coordinates=PortlandCoordinates(latitude=latitude, longitude=longitude),
                parcel_ids=PortlandParcelIds(
                    address_id=_string(address_id),
                    state_id=_normalize_state_id(_first_non_empty(state_id, taxlot_attrs.get("STATE_ID"), bds_attrs.get("STATE_ID"))),
                    tlid=_string(_first_non_empty(tlid, taxlot_attrs.get("TLID"))),
                    property_id=_string(_first_non_empty(property_id, taxlot_attrs.get("PROPERTYID"), bds_attrs.get("PROPERTY_ID"))),
                    county_property_id=_string(_first_non_empty(taxlot_attrs.get("RNO"), bds_attrs.get("PROPERTY_ID_MULTNOMAH_COUNTY"))),
                ),
                owner=_first_non_empty(taxlot_attrs.get("OWNER1"), bds_attrs.get("OWNER_NAME")),
                mailing_address=_build_mailing_address(taxlot_attrs, bds_attrs),
                legal_description=_first_non_empty(
                    taxlot_attrs.get("LEGAL_DESC"),
                    taxlot_attrs.get("LEGALDESC"),
                    bds_attrs.get("LEGAL_DESCRIPTION"),
                ),
                lot_metrics=PortlandLotMetrics(
                    acreage=_first_decimal(taxlot_attrs, "A_T_ACRES", "AREAACRES", "ACRES"),
                    lot_sqft=_first_decimal(taxlot_attrs, "A_T_SQFT", "AREASQFT", "AREA_SQ_FT", "AREA"),
                ),
                valuation=PortlandValuation(
                    land=land_value,
                    improvements=improvements_value,
                    total=total_value,
                ),
                zoning=_build_zoning_context(zoning_feature, overlay_features, bds_attrs),
                neighborhood=_first_non_empty(bds_attrs.get("NEIGHBORHOOD")),
                council_district=_first_non_empty(bds_attrs.get("COUNCIL_DISTRICT"), bds_attrs.get("COUNCILDIST")),
                business_district=_first_non_empty(bds_attrs.get("BUSINESS_DISTRICT"), bds_attrs.get("BUSINESSDIST")),
                hazard_flags=PortlandHazardFlags(
                    liquefaction=_to_bool_flag(_first_non_empty(bds_attrs.get("EARTHQUAKE_LIQUIFACTION_HAZARD"), bds_attrs.get("LIQUEFACTION"))),
                    floodway=_to_bool_flag(_first_non_empty(bds_attrs.get("FEMA_FLOOD_WAY"), bds_attrs.get("FLOODWAY"))),
                    flood_hazard=_to_bool_flag(_first_non_empty(bds_attrs.get("FEMA_SPECIAL_FLOOD_HAZARD_AREA"), bds_attrs.get("FLOOD_HAZARD"), bds_attrs.get("FLOODHAZARD"))),
                ),
                building_details=PortlandBuildingDetails(
                    use=_first_non_empty(
                        building_attrs.get("BUILDINGUSE"),
                        building_attrs.get("PROPERTYUSE"),
                        taxlot_attrs.get("PRPCD_DESC"),
                        taxlot_attrs.get("PROPERTYUSE"),
                        bds_attrs.get("BDS_PROPERTY_TYPE"),
                    ),
                    stories=_first_decimal(building_attrs, "STORIES", "FLOORS") or _first_decimal(taxlot_attrs, "FLOORS"),
                    sqft=_first_decimal(building_attrs, "BUILDINGSQFT", "BLDGSQFT", "SQFT") or _first_decimal(taxlot_attrs, "BLDGSQFT"),
                    year_built=_first_int(building_attrs, "YEARBUILT", "YEAR_BUILT") or _first_int(taxlot_attrs, "YEARBUILT"),
                    height_ft=_first_decimal(building_attrs, "HEIGHTFT", "HEIGHT_FT", "HEIGHT"),
                ),
            )
    except httpx.HTTPError as exc:
        raise PortlandMapsLookupError(f"ArcGIS request failed: {exc}") from exc


async def _safe_query_address_linkage(
    client: httpx.AsyncClient,
    *,
    base_url: str,
    matched_address: str | None,
    raw_x: float | None,
    raw_y: float | None,
) -> dict[str, Any] | None:
    if matched_address is None and (raw_x is None or raw_y is None):
        return None

    try:
        payload = await _get_json(
            client,
            f"{base_url}/COP_OpenData_Property/MapServer/47/query",
            params={
                "where": f"UPPER(FULL_ADDR) = '{_escape_sql((matched_address or '').upper())}'",
                "outFields": "*",
                "returnGeometry": "false",
                "f": "pjson",
            },
        )
        return _select_best_feature(_as_features(payload), matched_address=matched_address)
    except PortlandMapsLookupError:
        return None


async def _query_taxlot_feature(
    client: httpx.AsyncClient,
    *,
    base_url: str,
    state_id: str | None,
    property_id: str | None,
    tlid: str | None,
    raw_x: float | None,
    raw_y: float | None,
) -> dict[str, Any] | None:
    where_clauses = []
    if state_id:
        where_clauses.append(f"STATE_ID = '{_escape_sql(state_id)}'")
    if property_id:
        where_clauses.append(f"PROPERTYID = '{_escape_sql(property_id)}'")
        where_clauses.append(f"PROPERTY_ID = '{_escape_sql(property_id)}'")
    if tlid:
        where_clauses.append(f"TLID = '{_escape_sql(tlid)}'")

    for where in where_clauses:
        payload = await _get_json(
            client,
            f"{base_url}/Public/Taxlots/MapServer/0/query",
            params={
                "where": where,
                "outFields": "*",
                "returnGeometry": "false",
                "f": "pjson",
            },
        )
        features = _as_features(payload)
        if features:
            return features[0]

    features = await _safe_query_point_features(
        client,
        f"{base_url}/Public/Taxlots/MapServer/0/query",
        raw_x=raw_x,
        raw_y=raw_y,
    )
    return features[0] if features else None


async def _safe_query_point_features(
    client: httpx.AsyncClient,
    url: str,
    *,
    raw_x: float | None,
    raw_y: float | None,
) -> list[dict[str, Any]]:
    if raw_x is None or raw_y is None:
        return []
    try:
        payload = await _get_json(
            client,
            url,
            params={
                "geometry": f"{raw_x},{raw_y}",
                "geometryType": "esriGeometryPoint",
                "inSR": 3857,
                "spatialRel": "esriSpatialRelIntersects",
                "outFields": "*",
                "returnGeometry": "false",
                "f": "pjson",
            },
        )
        return _as_features(payload)
    except PortlandMapsLookupError:
        return []


async def _get_json(
    client: httpx.AsyncClient,
    url: str,
    *,
    params: dict[str, Any],
) -> dict[str, Any]:
    try:
        response = await client.get(url, params=params)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise PortlandMapsLookupError(f"ArcGIS request failed for {url}: {exc}") from exc

    try:
        payload = response.json()
    except ValueError as exc:
        raise PortlandMapsLookupError(f"ArcGIS response was not valid JSON for {url}") from exc

    if not isinstance(payload, dict):
        raise PortlandMapsLookupError(f"ArcGIS response for {url} was not a JSON object")

    _raise_if_arcgis_error(payload)
    return payload


def _raise_if_arcgis_error(payload: dict[str, Any]) -> None:
    error = payload.get("error")
    if not isinstance(error, dict):
        return
    message = error.get("message") or "ArcGIS REST query failed"
    details = error.get("details") or []
    detail_text = f" ({'; '.join(str(item) for item in details if item)})" if details else ""
    raise PortlandMapsLookupError(f"{message}{detail_text}")


def _select_candidate(
    candidates: list[dict[str, Any]],
    normalized_input: str,
) -> tuple[dict[str, Any] | None, bool]:
    if not candidates:
        return None, False

    exact_matches = [
        candidate
        for candidate in candidates
        if _normalized_address_text(_first_non_empty(candidate.get("address"), _feature_attributes(candidate).get("Match_addr")))
        == normalized_input
    ]
    unique_exact_addresses = {
        _first_non_empty(candidate.get("address"), _feature_attributes(candidate).get("Match_addr"))
        for candidate in exact_matches
    }
    if len(unique_exact_addresses) > 1:
        return None, True
    if exact_matches:
        return exact_matches[0], False

    ranked = sorted(candidates, key=lambda item: _to_float(_feature_attributes(item).get("Score") or item.get("score")) or 0.0, reverse=True)
    if len(ranked) >= 2:
        top_score = _to_float(_feature_attributes(ranked[0]).get("Score") or ranked[0].get("score"))
        second_score = _to_float(_feature_attributes(ranked[1]).get("Score") or ranked[1].get("score"))
        if top_score is not None and second_score is not None and abs(top_score - second_score) < 1e-9:
            first_address = _first_non_empty(ranked[0].get("address"), _feature_attributes(ranked[0]).get("Match_addr"))
            second_address = _first_non_empty(ranked[1].get("address"), _feature_attributes(ranked[1]).get("Match_addr"))
            if _normalized_address_text(first_address) != _normalized_address_text(second_address):
                return None, True
    return ranked[0], False


def _select_best_feature(
    features: list[dict[str, Any]],
    *,
    state_id: str | None = None,
    address_id: str | None = None,
    property_id: str | None = None,
    matched_address: str | None = None,
) -> dict[str, Any] | None:
    if not features:
        return None

    normalized_state = _normalize_state_id(state_id)
    normalized_address = _normalized_address_text(matched_address)
    normalized_property_id = _normalized_address_text(property_id)

    for feature in features:
        attrs = _feature_attributes(feature)
        if normalized_state and _normalize_state_id(_first_non_empty(attrs.get("STATE_ID"), attrs.get("PROPGISID1"))) == normalized_state:
            return feature
    for feature in features:
        attrs = _feature_attributes(feature)
        if address_id and _string(attrs.get("ADDRESS_ID")) == _string(address_id):
            return feature
    for feature in features:
        attrs = _feature_attributes(feature)
        if normalized_property_id and _normalized_address_text(_first_non_empty(attrs.get("PROPERTY_ID"), attrs.get("PROPERTYID"))) == normalized_property_id:
            return feature
    for feature in features:
        attrs = _feature_attributes(feature)
        feature_address = _normalized_address_text(
            _first_non_empty(attrs.get("ADDRESS_SITUS"), attrs.get("SITEADDR"), attrs.get("FULL_ADDR"))
        )
        if normalized_address and feature_address == normalized_address:
            return feature
    return features[0]


def _build_mailing_address(
    taxlot_attrs: dict[str, Any],
    bds_attrs: dict[str, Any],
) -> PortlandMailingAddress | None:
    street = _first_non_empty(taxlot_attrs.get("OWNERADDR"), taxlot_attrs.get("OWNERADDR1"))
    city = _first_non_empty(taxlot_attrs.get("OWNERCITY"))
    state = _first_non_empty(taxlot_attrs.get("OWNERSTATE"))
    zip_code = _first_non_empty(taxlot_attrs.get("OWNERZIP"))
    if street or city or state or zip_code:
        return PortlandMailingAddress(street=street, city=city, state=state, zip_code=zip_code)

    mailing_text = _first_non_empty(bds_attrs.get("OWNER_MAILING_ADDRESS"))
    if not mailing_text:
        return None

    parsed = _parse_owner_mailing_address(mailing_text)
    return PortlandMailingAddress(**parsed) if any(parsed.values()) else None


def _build_zoning_context(
    zoning_feature: dict[str, Any] | None,
    overlay_features: list[dict[str, Any]],
    bds_attrs: dict[str, Any],
) -> PortlandZoningContext | None:
    zoning_attrs = _feature_attributes(zoning_feature)
    overlays = _collect_overlays(zoning_attrs, overlay_features)
    if not zoning_attrs and not bds_attrs and not overlays:
        return None

    return PortlandZoningContext(
        code=_first_non_empty(zoning_attrs.get("ZONE"), zoning_attrs.get("BASEZONE"), bds_attrs.get("ZONE")),
        description=_first_non_empty(zoning_attrs.get("ZONE_DESC"), zoning_attrs.get("BASEDESC")),
        comp_plan=_first_non_empty(
            zoning_attrs.get("CMP_DESC"),
            zoning_attrs.get("COMPLAN"),
            zoning_attrs.get("CMP"),
            bds_attrs.get("BPS_COMMUNITY_PLAN_ADOPTED"),
        ),
        overlays=overlays,
        plan_district=_first_non_empty(
            zoning_attrs.get("PLDIST_DESC"),
            zoning_attrs.get("PLANDIST"),
            zoning_attrs.get("PLDIST"),
            bds_attrs.get("PLAN_DISTRICT"),
        ),
    )


def _collect_overlays(zoning_attrs: dict[str, Any], overlay_features: list[dict[str, Any]]) -> list[str]:
    values: list[str] = []
    for key in ("OVERLAY", "OVRLY", "OVRLY_DESC", "CMPOVR", "CMPOVR_DESC", "HIST", "HIST_DESC", "CONSV", "CONSV_DESC"):
        text = _string(zoning_attrs.get(key))
        if text:
            values.append(text)

    for feature in overlay_features:
        attrs = _feature_attributes(feature)
        for key in ("OVERLAY", "OVRLY", "OVERLAY_DESC", "OVRLY_DESC", "NAME", "LABEL"):
            text = _string(attrs.get(key))
            if text:
                values.append(text)

    deduped: list[str] = []
    seen: set[str] = set()
    for value in values:
        key = value.strip().lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(value)
    return deduped


def _best_total_value(
    taxlot_attrs: dict[str, Any],
    land_value: Decimal | None,
    improvements_value: Decimal | None,
) -> Decimal | None:
    for key in ("TOTALVAL", "TOTALVAL3", "TOTALVAL2", "TOTALVAL1"):
        value = _to_decimal(taxlot_attrs.get(key))
        if value not in (None, Decimal("0")):
            return value
    if land_value is None and improvements_value is None:
        return None
    return (land_value or Decimal("0")) + (improvements_value or Decimal("0"))


def _parse_owner_mailing_address(value: str) -> dict[str, str | None]:
    cleaned = " ".join(str(value).replace("%", " ").split())
    match = re.search(r"(?P<street>.+?)\s+(?P<city>[A-Z][A-Z\s]+)\s+(?P<state>[A-Z]{2})\s+(?P<zip>\d{5}(?:-\d{4})?)$", cleaned)
    if not match:
        return {"street": cleaned or None, "city": None, "state": None, "zip_code": None}
    return {
        "street": match.group("street").strip() or None,
        "city": match.group("city").strip() or None,
        "state": match.group("state").strip() or None,
        "zip_code": match.group("zip").strip() or None,
    }


def _feature_attributes(feature: Any) -> dict[str, Any]:
    if not isinstance(feature, dict):
        return {}
    attributes = feature.get("attributes")
    if isinstance(attributes, dict):
        return attributes
    return feature


def _as_features(payload: dict[str, Any]) -> list[dict[str, Any]]:
    features = payload.get("features") or []
    if not isinstance(features, list):
        return []
    return [item for item in features if isinstance(item, dict)]


def _escape_sql(value: str) -> str:
    return value.replace("'", "''")


def _normalize_state_id(value: Any) -> str | None:
    text = _string(value)
    if text is None:
        return None
    return " ".join(text.split())


def _normalized_address_text(value: Any) -> str:
    text = _string(value)
    if text is None:
        return ""
    return " ".join(text.upper().replace(",", " ").split())


def _first_non_empty(*values: Any) -> str | None:
    for value in values:
        text = _string(value)
        if text:
            return text
    return None


def _string(value: Any) -> str | None:
    if value in (None, ""):
        return None
    text = str(value).strip()
    return text or None


def _to_decimal(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value).replace(",", "").replace("$", ""))
    except (InvalidOperation, ValueError):
        return None


def _to_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _first_decimal(source: dict[str, Any], *keys: str) -> Decimal | None:
    for key in keys:
        value = _to_decimal(source.get(key))
        if value is not None:
            return value
    return None


def _first_int(source: dict[str, Any], *keys: str) -> int | None:
    for key in keys:
        value = source.get(key)
        if value in (None, ""):
            continue
        try:
            return int(float(str(value).replace(",", "")))
        except (TypeError, ValueError):
            continue
    return None


def _to_bool_flag(value: Any) -> bool | None:
    text = _string(value)
    if text is None:
        return None
    normalized = text.lower()
    if normalized in {"yes", "y", "true", "1"}:
        return True
    if normalized in {"no", "n", "false", "0"}:
        return False
    return None


def _coerce_lat_lon(raw_x: float | None, raw_y: float | None) -> tuple[float | None, float | None]:
    if raw_x is None or raw_y is None:
        return None, None
    if abs(raw_x) > 180 or abs(raw_y) > 90:
        longitude = raw_x * 180.0 / 20037508.34
        latitude = math.degrees(2.0 * math.atan(math.exp(raw_y / 6378137.0)) - math.pi / 2.0)
        return latitude, longitude
    return raw_y, raw_x


__all__ = ["PortlandMapsLookupError", "lookup_portland_parcel"]
