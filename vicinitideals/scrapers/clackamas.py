"""Clackamas County exact-address lookup helpers via the Jericho API."""

from __future__ import annotations

from typing import Any, Literal

import httpx

from vicinitideals.config import settings
from vicinitideals.schemas.parcel import ClackamasParcelResult
from vicinitideals.utils.proxy_pool import gis_proxy


class ClackamasLookupError(RuntimeError):
    """Raised when the Clackamas Jericho API cannot be queried successfully."""


async def lookup_clackamas_parcel(address: str) -> ClackamasParcelResult:
    """Resolve one Clackamas County address into normalized parcel, zoning, and UGB facts."""
    normalized_address = " ".join(address.split())
    if not normalized_address:
        raise ClackamasLookupError("Address is required for Clackamas lookup")

    base_url = settings.clackamas_maps_base_url.rstrip("/")
    timeout = httpx.Timeout(settings.clackamas_maps_timeout_seconds)

    async with httpx.AsyncClient(timeout=timeout, proxy=gis_proxy()) as client:
        address_payload = await _post_form(
            client,
            f"{base_url}/jericho/data/query/address",
            {"q": normalized_address},
        )
        matches = _extract_results(address_payload)
        if not matches:
            return ClackamasParcelResult(
                input_address=normalized_address,
                match_status="no_match",
            )

        first_match = matches[0]
        point_geometry = _point_geometry(first_match)
        result = ClackamasParcelResult(
            input_address=normalized_address,
            match_status="single_match",
            primary_address=_string(first_match.get("name")),
        )

        taxlot_payload = await _post_form(
            client,
            f"{base_url}/jericho/data/select/taxlot",
            {"geometry": point_geometry},
        )
        _apply_taxlot_features(result, _extract_features(taxlot_payload))

        development_payload = await _post_form(
            client,
            f"{base_url}/jericho/data/select/development",
            {"geometry": point_geometry},
        )
        _apply_development_features(result, _extract_features(development_payload))

        await _apply_optional_enrichments(
            client,
            base_url=base_url,
            geometry=point_geometry,
            result=result,
        )
        return result


async def _apply_optional_enrichments(
    client: httpx.AsyncClient,
    *,
    base_url: str,
    geometry: str,
    result: ClackamasParcelResult,
) -> None:
    await _apply_environmental_enrichment(client, base_url=base_url, geometry=geometry, result=result)
    await _apply_utilities_enrichment(client, base_url=base_url, geometry=geometry, result=result)


async def _apply_environmental_enrichment(
    client: httpx.AsyncClient,
    *,
    base_url: str,
    geometry: str,
    result: ClackamasParcelResult,
) -> None:
    try:
        payload = await _post_form(
            client,
            f"{base_url}/jericho/data/select/environmental",
            {"geometry": geometry},
        )
    except ClackamasLookupError:
        return

    for feature in _extract_features(payload):
        properties = _feature_properties(feature)
        if _normalize_key(properties.get("datagroup")) == "flood":
            result.flood_hazard = _string(properties.get("hazard_value"))
            return


async def _apply_utilities_enrichment(
    client: httpx.AsyncClient,
    *,
    base_url: str,
    geometry: str,
    result: ClackamasParcelResult,
) -> None:
    try:
        payload = await _post_form(
            client,
            f"{base_url}/jericho/data/select/utilities",
            {"geometry": geometry},
        )
    except ClackamasLookupError:
        return

    for feature in _extract_features(payload):
        properties = _feature_properties(feature)
        datagroup = _normalize_key(properties.get("datagroup"))
        service_name = _string(properties.get("service_name"))
        if datagroup == "school_district" and service_name:
            result.school_district = service_name
        elif datagroup == "community_planning_organization" and service_name:
            result.planning_org = service_name


async def _post_form(
    client: httpx.AsyncClient,
    url: str,
    data: dict[str, Any],
) -> dict[str, Any]:
    try:
        response = await client.post(
            url,
            data=data,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/x-www-form-urlencoded",
            },
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise ClackamasLookupError(f"Jericho request failed for {url}: {exc}") from exc

    try:
        payload = response.json()
    except ValueError as exc:
        raise ClackamasLookupError(f"Jericho response was not valid JSON for {url}") from exc

    if not isinstance(payload, dict):
        raise ClackamasLookupError(f"Jericho response for {url} was not a JSON object")
    return payload


def _extract_results(payload: dict[str, Any]) -> list[dict[str, Any]]:
    raw_results = payload.get("results") or payload.get("result") or []
    if not isinstance(raw_results, list):
        return []
    return [item for item in raw_results if isinstance(item, dict)]


def _extract_features(payload: dict[str, Any]) -> list[dict[str, Any]]:
    raw_features = payload.get("features") or payload.get("results") or payload.get("result") or []
    if not isinstance(raw_features, list):
        return []
    return [item for item in raw_features if isinstance(item, dict)]


def _apply_taxlot_features(result: ClackamasParcelResult, features: list[dict[str, Any]]) -> None:
    properties = _feature_properties(features[0]) if features else {}
    if not properties:
        return

    result.primary_address = _first_non_empty(properties.get("primary_address"), result.primary_address)
    result.jurisdiction = _string(properties.get("jurisdiction"))
    result.map_number = _string(properties.get("map_number"))
    result.taxlot_number = _string(properties.get("taxlot_number"))
    result.parcel_number = _string(properties.get("parcel_number"))
    result.document_number = _string(properties.get("document_number"))
    result.census_tract = _string(properties.get("census_tract"))
    result.landclass = _string(properties.get("landclass"))


def _apply_development_features(result: ClackamasParcelResult, features: list[dict[str, Any]]) -> None:
    designation: str | None = None
    ugb_raw: str | None = None
    zoning_url: str | None = None

    for feature in features:
        properties = _feature_properties(feature)
        classification = _string(properties.get("classification"))
        if not classification:
            continue

        label, _, raw_value = classification.partition(":")
        value = raw_value.strip() or None
        label_key = _normalize_key(label)
        if label_key == "designation":
            designation = value
            zoning_url = _first_non_empty(properties.get("web_url"), zoning_url)
        elif label_key == "urban_growth_boundary":
            ugb_raw = value

    result.zoning_label = _zoning_label(result.jurisdiction, designation)
    result.zoning_value = designation
    result.zoning_url = zoning_url
    result.ugb_raw = ugb_raw
    result.ugb_status = _ugb_status(ugb_raw)


def _feature_properties(feature: dict[str, Any]) -> dict[str, Any]:
    properties = feature.get("properties")
    return properties if isinstance(properties, dict) else {}


def _point_geometry(match: dict[str, Any]) -> str:
    for candidate in (match.get("point"), match.get("geometry"), match.get("geom")):
        if isinstance(candidate, str):
            text = candidate.strip()
            if text:
                return text if text.upper().startswith("POINT(") else text
        if isinstance(candidate, dict):
            coordinates = candidate.get("coordinates")
            if isinstance(coordinates, (list, tuple)) and len(coordinates) >= 2:
                return f"POINT({coordinates[0]} {coordinates[1]})"
    raise ClackamasLookupError("Address lookup did not return a usable point geometry")


def _zoning_label(jurisdiction: str | None, designation: str | None) -> str | None:
    if not designation:
        return None
    if designation.strip().lower() == "contact city":
        return "City Zoning"
    if (jurisdiction or "").strip().lower() == "clackamas county":
        return "County Zoning"
    return "City Zoning"


def _ugb_status(ugb_raw: str | None) -> Literal["inside", "outside"] | None:
    normalized = (ugb_raw or "").strip().upper()
    if normalized == "METRO UGB":
        return "inside"
    if normalized == "OUTSIDE":
        return "outside"
    return None


def _normalize_key(value: Any) -> str:
    return "_".join(str(value or "").strip().lower().replace("-", " ").split())


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


__all__ = ["ClackamasLookupError", "lookup_clackamas_parcel"]
