"""Parcel lookup endpoints."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass

from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import or_, select

from app.api.deps import DBSession
from app.models.parcel import Parcel
from app.reconciliation.matcher import normalize_apn
from app.schemas.parcel import (
    ClackamasLookupRequest,
    ClackamasParcelResult,
    GreshamLookupParcel,
    OregonCityLookupRequest,
    OregonCityParcelResult,
    ParcelLookupRequest,
    ParcelLookupResponse,
    ParcelLookupResult,
    ParcelRead,
    PortlandLookupRequest,
    PortlandParcelResult,
)
from app.scrapers.arcgis import ArcGISLookupError, lookup_gresham_parcels
from app.scrapers.clackamas import ClackamasLookupError, lookup_clackamas_parcel
from app.scrapers.oregoncity import OregonCityLookupError, lookup_oregoncity_parcel
from app.scrapers.portlandmaps import PortlandMapsLookupError, lookup_portland_parcel

router = APIRouter(tags=["parcels"])


def _build_parcel_stmt(
    *,
    address: str | None = None,
    apn: str | None = None,
    zoning: str | None = None,
):
    stmt = select(Parcel).order_by(Parcel.address_normalized.asc().nullslast(), Parcel.apn.asc())

    if address:
        pattern = f"%{address.strip()}%"
        stmt = stmt.where(
            or_(
                Parcel.address_normalized.ilike(pattern),
                Parcel.address_raw.ilike(pattern),
            )
        )
    if apn:
        # Match both the raw APN (preserves punctuation/whitespace for partial
        # state-format searches like "1S3E10AD") AND the normalized form, so a
        # query with dashes/spaces like "1S3E10AD -05800" still finds the row
        # even when the stored canonical APN uses a different punctuation style.
        apn_query = apn.strip()
        apn_compact = normalize_apn(apn_query)
        clauses = [Parcel.apn.ilike(f"%{apn_query}%")]
        if apn_compact:
            clauses.append(Parcel.apn_normalized.ilike(f"%{apn_compact}%"))
        stmt = stmt.where(or_(*clauses))
    if zoning:
        pattern = f"%{zoning.strip()}%"
        stmt = stmt.where(
            or_(
                Parcel.zoning_code.ilike(pattern),
                Parcel.zoning_description.ilike(pattern),
            )
        )
    return stmt


async def _query_cached_parcels(
    session: DBSession,
    *,
    address: str | None = None,
    apn: str | None = None,
) -> list[Parcel]:
    result = await session.execute(_build_parcel_stmt(address=address, apn=apn))
    return list(result.scalars())


async def _upsert_parcel(session: DBSession, parcel_data: dict) -> Parcel:
    from app.scrapers.parcel_enrichment import _upsert_parcel as _core_upsert
    return await _core_upsert(session, parcel_data)


def _as_parcel_reads(parcels: list[Parcel]) -> list[ParcelRead]:
    return [ParcelRead.model_validate(parcel) for parcel in parcels]


def _coerce_lookup_result(result: Any) -> ParcelLookupResult:
    if isinstance(result, ParcelLookupResult):
        return result
    if is_dataclass(result):
        return ParcelLookupResult.model_validate(asdict(result))
    return ParcelLookupResult.model_validate(result)


def _lookup_parcel_to_record(parcel: GreshamLookupParcel | dict[str, Any]) -> dict[str, Any]:
    data = parcel if isinstance(parcel, dict) else parcel.model_dump(mode="python")
    owner_parts = [data.get("owner_street"), data.get("owner_city"), data.get("owner_state"), data.get("owner_zip")]
    owner_mailing = ", ".join(
        str(part).strip()
        for part in owner_parts
        if part not in (None, "") and str(part).strip()
    ) or None
    return {
        "apn": data.get("rno"),
        "state_id": data.get("state_id"),
        "address_normalized": data.get("site_address"),
        "address_raw": data.get("site_address"),
        "owner_name": data.get("owner_name"),
        "owner_mailing_address": owner_mailing,
        "owner_street": data.get("owner_street"),
        "owner_city": data.get("owner_city"),
        "owner_state": data.get("owner_state"),
        "owner_zip": data.get("owner_zip"),
        "lot_sqft": data.get("sqft"),
        "gis_acres": data.get("gis_acres"),
        "zoning_code": data.get("zone"),
        "zoning_description": data.get("zone"),
        "current_use": data.get("land_use"),
        "assessed_value_land": data.get("land_value"),
        "assessed_value_improvements": data.get("building_value"),
        "total_assessed_value": data.get("total_value"),
        "tax_code": data.get("tax_code"),
        "legal_description": data.get("legal_description"),
        "year_built": data.get("year_built"),
        "building_sqft": data.get("building_sqft"),
        "geometry": data.get("geometry"),
    }


@router.get("/parcels", response_model=list[ParcelRead])
async def list_parcels(
    session: DBSession,
    address: str | None = Query(default=None),
    apn: str | None = Query(default=None),
    zoning: str | None = Query(default=None),
) -> list[Parcel]:
    result = await session.execute(_build_parcel_stmt(address=address, apn=apn, zoning=zoning))
    return list(result.scalars())


@router.post("/parcels/lookup", response_model=ParcelLookupResponse)
async def lookup_parcels(
    payload: ParcelLookupRequest,
    session: DBSession,
) -> ParcelLookupResponse:
    try:
        results = [_coerce_lookup_result(result) for result in await lookup_gresham_parcels(payload.addresses)]
    except ArcGISLookupError as exc:
        raise HTTPException(status_code=502, detail=f"Gresham lookup failed: {exc}") from exc

    for result in results:
        for parcel in result.parcels:
            record = _lookup_parcel_to_record(parcel)
            if record.get("apn"):
                await _upsert_parcel(session, record)

    return ParcelLookupResponse(results=results)


@router.post("/parcels/lookup/clackamas", response_model=ClackamasParcelResult)
async def lookup_clackamas(payload: ClackamasLookupRequest) -> ClackamasParcelResult:
    try:
        return await lookup_clackamas_parcel(payload.address)
    except ClackamasLookupError as exc:
        raise HTTPException(status_code=502, detail=f"Clackamas lookup failed: {exc}") from exc


@router.post("/parcels/lookup/oregoncity", response_model=OregonCityParcelResult)
async def lookup_oregoncity(payload: OregonCityLookupRequest) -> OregonCityParcelResult:
    try:
        return await lookup_oregoncity_parcel(payload.address)
    except OregonCityLookupError as exc:
        raise HTTPException(status_code=502, detail=f"Oregon City lookup failed: {exc}") from exc


@router.post("/parcels/lookup/portland", response_model=PortlandParcelResult)
async def lookup_portland(payload: PortlandLookupRequest) -> PortlandParcelResult:
    try:
        return await lookup_portland_parcel(payload.address)
    except PortlandMapsLookupError as exc:
        raise HTTPException(status_code=502, detail=f"Portland lookup failed: {exc}") from exc


@router.get("/parcels/{parcel_id}", response_model=ParcelRead)
async def get_parcel(parcel_id: UUID, session: DBSession) -> Parcel:
    parcel = await session.get(Parcel, parcel_id)
    if parcel is None:
        raise HTTPException(status_code=404, detail="Parcel not found")
    return parcel
