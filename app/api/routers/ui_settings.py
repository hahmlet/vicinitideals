"""Settings, billing, scraping-services, and source-vehicle routes.

Extracted from ui.py (Phase 2a). Covers:
  /  /splash  /settings/*  /mock/billing/*  /ui/admin/*
  /settings/vehicles/*
"""
from __future__ import annotations

import asyncio
import time
import uuid as _uuid_mod
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from urllib.parse import quote_plus, urlencode
from uuid import UUID
from zoneinfo import ZoneInfo

import httpx
from fastapi import APIRouter, Form, HTTPException, Query, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import DBSession
from app.config import settings
from app.models.capital import CapitalModule
from app.models.ingestion import IngestJob
from app.models.org import Organization, User
from app.models.scraped_listing import ScrapedListing
from app.models.settings import UserSetting
from app.api.routers.ui_helpers import (
    _base_ctx,
    _get_address_issues_count,
    _get_counts,
    _get_user,
    _require_settings_owner,
    templates,
)

router = APIRouter(include_in_schema=False)

# ---------------------------------------------------------------------------
# Module-level state
# ---------------------------------------------------------------------------

_PACIFIC = ZoneInfo("America/Los_Angeles")
_PROXYON_STATUS_CACHE_TTL_SECONDS = 3600
_proxyon_status_lock = asyncio.Lock()
_proxyon_status_cache: dict[str, Any] = {
    "fetched_monotonic": 0.0,
    "status_label": "Not Configured",
    "connected": False,
    "remaining_gb": None,
    "expected_days_left": None,
    "account_balance_usd": None,
    "active_subscription_id": None,
    "datacenter_count_live": None,   # active proxies from /datacenter/list
    "datacenter_by_country": None,   # dict {"us": 5, ...} from live list
    "checked_at": None,
}


# ---------------------------------------------------------------------------
# Settings / billing / ProxyOn helpers
# ---------------------------------------------------------------------------

def _stripe_secret_key() -> str:
    return (settings.stripe_secret_key or "").strip()


def _stripe_publishable_key() -> str:
    return (settings.stripe_publishable_key or "").strip()


def _stripe_is_configured() -> bool:
    return bool(_stripe_secret_key())


def _stripe_price_catalog() -> dict[str, str]:
    return {
        "pro_monthly": (settings.stripe_price_pro_monthly or "").strip(),
        "pro_annual": (settings.stripe_price_pro_annual or "").strip(),
    }


def _stripe_price_label(price_id: str | None) -> str:
    price = (price_id or "").strip()
    if not price:
        return "Free Trial"
    catalog = _stripe_price_catalog()
    if catalog.get("pro_monthly") and catalog["pro_monthly"] == price:
        return "Pro Monthly"
    if catalog.get("pro_annual") and catalog["pro_annual"] == price:
        return "Pro Annual"
    return "Custom"


def _stripe_state_message(state: str | None) -> str | None:
    if state == "success":
        return "Stripe action completed successfully."
    if state == "cancel":
        return "Stripe checkout was cancelled before completion."
    if state == "config-missing":
        return "Billing is not configured yet. Add Stripe keys in environment settings first."
    if state == "cancel-scheduled":
        return "Subscription cancellation is scheduled for the end of the billing period."
    if state == "reactivated":
        return "Cancellation was removed. Subscription remains active."
    if state == "no-subscription":
        return "No active Stripe subscription was found for this account."
    if state == "already-cancelled":
        return "This subscription is already cancelled."
    if state == "card-default-updated":
        return "Default payment card updated."
    if state == "card-removed":
        return "Payment card removed."
    if state == "card-remove-error":
        return "Could not remove that payment card right now."
    if state == "error":
        return "Stripe returned an error while starting checkout. Try again in a moment."
    return None


async def _stripe_api_request(
    method: str,
    endpoint: str,
    *,
    data: dict[str, Any] | list[tuple[str, str]] | None = None,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    api_key = _stripe_secret_key()
    if not api_key:
        raise HTTPException(status_code=400, detail="Stripe is not configured")

    url = f"https://api.stripe.com{endpoint}"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",
    }
    timeout = httpx.Timeout(20.0)

    def _send() -> httpx.Response:
        req_data: dict[str, Any] | None = None
        req_content: bytes | None = None
        req_headers = dict(headers)
        if isinstance(data, list):
            req_content = urlencode(data).encode("utf-8")
            req_headers["Content-Type"] = "application/x-www-form-urlencoded"
        else:
            req_data = data

        with httpx.Client(timeout=timeout, trust_env=False) as client:
            return client.request(
                method,
                url,
                headers=req_headers,
                data=req_data,
                content=req_content,
                params=params,
            )

    try:
        resp = await asyncio.to_thread(_send)
    except Exception as exc:  # pragma: no cover - network exception guard
        raise HTTPException(status_code=502, detail=f"Stripe connection failed: {exc}") from exc

    body: dict[str, Any]
    try:
        body = resp.json()
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Stripe returned a non-JSON response") from exc

    if resp.status_code >= 400:
        err = body.get("error") if isinstance(body, dict) else None
        err_msg = (err or {}).get("message") if isinstance(err, dict) else None
        raise HTTPException(status_code=502, detail=f"Stripe API error: {err_msg or 'unknown error'}")

    return body


async def _get_stripe_customer_id(session: AsyncSession, user_id: UUID) -> str | None:
    row = (
        await session.execute(
            select(UserSetting).where(
                UserSetting.user_id == user_id,
                UserSetting.field_key == "stripe_customer_id",
            )
        )
    ).scalar_one_or_none()
    if row is None:
        return None
    value = (row.value or "").strip()
    return value or None


async def _clear_stripe_customer_id(session: AsyncSession, user_id: UUID) -> None:
    row = (
        await session.execute(
            select(UserSetting).where(
                UserSetting.user_id == user_id,
                UserSetting.field_key == "stripe_customer_id",
            )
        )
    ).scalar_one_or_none()
    if row is None:
        return
    await session.delete(row)
    await session.commit()


async def _ensure_stripe_customer_id(session: AsyncSession, user: User) -> str:
    existing_id = await _get_stripe_customer_id(session, user.id)
    if existing_id:
        return existing_id

    payload: list[tuple[str, str]] = [
        ("name", user.name or "Viciniti Deals user"),
        ("metadata[user_id]", str(user.id)),
        ("metadata[org_id]", str(user.org_id)),
    ]
    if user.email:
        payload.append(("email", user.email))

    customer = await _stripe_api_request("POST", "/v1/customers", data=payload)
    customer_id = str(customer.get("id") or "").strip()
    if not customer_id:
        raise HTTPException(status_code=502, detail="Stripe customer creation failed")

    row = UserSetting(
        id=_uuid_mod.uuid4(),
        user_id=user.id,
        org_id=user.org_id,
        field_key="stripe_customer_id",
        value=customer_id,
    )
    session.add(row)
    await session.commit()
    return customer_id


async def _get_customer_default_payment_method(customer_id: str) -> str | None:
    customer = await _stripe_api_request("GET", f"/v1/customers/{customer_id}")
    default_pm = str(((customer.get("invoice_settings") or {}).get("default_payment_method") or "")).strip()
    return default_pm or None


async def _list_stripe_payment_methods(customer_id: str) -> list[dict[str, str]]:
    default_pm = await _get_customer_default_payment_method(customer_id)
    body = await _stripe_api_request(
        "GET",
        "/v1/payment_methods",
        params={"customer": customer_id, "type": "card", "limit": 5},
    )

    rows: list[dict[str, str]] = []
    for item in body.get("data", []):
        card = item.get("card") or {}
        brand = str(card.get("brand") or "card").title()
        last4 = str(card.get("last4") or "••••")
        exp_month = str(card.get("exp_month") or "").zfill(2)
        exp_year = str(card.get("exp_year") or "")
        rows.append(
            {
                "id": str(item.get("id") or "").strip(),
                "brand": brand,
                "last4": last4,
                "exp": f"{exp_month}/{exp_year}" if exp_month and exp_year else "",
                "is_default": bool(default_pm and default_pm == str(item.get("id") or "").strip()),
            }
        )
    return rows


async def _get_stripe_subscription_summary(customer_id: str) -> dict[str, Any] | None:
    body = await _stripe_api_request(
        "GET",
        "/v1/subscriptions",
        params={"customer": customer_id, "status": "all", "limit": 10},
    )
    subs = [s for s in body.get("data", []) if isinstance(s, dict)]
    if not subs:
        return None

    status_rank = {
        "active": 0,
        "trialing": 1,
        "past_due": 2,
        "incomplete": 3,
        "unpaid": 4,
        "canceled": 9,
    }
    subs.sort(key=lambda s: status_rank.get(str(s.get("status") or ""), 5))
    sub = subs[0]

    items = ((sub.get("items") or {}).get("data") or [])
    first_item = items[0] if items else {}
    price = first_item.get("price") or {}
    price_id = str((price.get("id") or "")).strip()
    interval = str(((price.get("recurring") or {}).get("interval") or "")).strip() or "month"

    quantity = 1
    try:
        quantity = int(first_item.get("quantity") or 1)
    except Exception:
        quantity = 1

    current_period_end: datetime | None = None
    raw_period_end = sub.get("current_period_end")
    try:
        if raw_period_end is not None:
            current_period_end = datetime.fromtimestamp(int(raw_period_end), UTC)
    except Exception:
        current_period_end = None

    trial_end: datetime | None = None
    raw_trial_end = sub.get("trial_end")
    try:
        if raw_trial_end is not None:
            trial_end = datetime.fromtimestamp(int(raw_trial_end), UTC)
    except Exception:
        trial_end = None

    return {
        "id": str(sub.get("id") or "").strip(),
        "status": str(sub.get("status") or "unknown"),
        "cancel_at_period_end": bool(sub.get("cancel_at_period_end")),
        "current_period_end": current_period_end,
        "trial_end": trial_end,
        "item_id": str(first_item.get("id") or "").strip(),
        "price_id": price_id,
        "interval": interval,
        "quantity": quantity,
        "plan_label": _stripe_price_label(price_id),
    }


async def _upsert_user_setting(
    session: AsyncSession,
    *,
    user: User,
    field_key: str,
    value: str,
) -> None:
    row = (
        await session.execute(
            select(UserSetting).where(
                UserSetting.user_id == user.id,
                UserSetting.field_key == field_key,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        row = UserSetting(
            id=_uuid_mod.uuid4(),
            user_id=user.id,
            org_id=user.org_id,
            field_key=field_key,
            value=value,
        )
        session.add(row)
    else:
        row.value = value
        session.add(row)


async def _sync_user_billing_snapshot(
    session: AsyncSession,
    *,
    user: User,
    subscription: dict[str, Any] | None,
) -> None:
    if not subscription:
        values = {
            "billing_scope": "user",
            "billing_plan": "free_trial",
            "billing_status": "none",
            "billing_interval": "none",
            "billing_seats": "1",
            "billing_subscription_id": "",
            "billing_price_id": "",
            "billing_cancel_at_period_end": "false",
            "billing_current_period_end": "",
            "billing_trial_end": "",
        }
    else:
        current_period_end = subscription.get("current_period_end")
        trial_end = subscription.get("trial_end")
        interval = str(subscription.get("interval") or "month")
        values = {
            "billing_scope": "user",
            "billing_plan": "pro",
            "billing_status": str(subscription.get("status") or "unknown"),
            "billing_interval": "annual" if interval == "year" else "monthly",
            "billing_seats": str(subscription.get("quantity") or 1),
            "billing_subscription_id": str(subscription.get("id") or ""),
            "billing_price_id": str(subscription.get("price_id") or ""),
            "billing_cancel_at_period_end": "true" if subscription.get("cancel_at_period_end") else "false",
            "billing_current_period_end": current_period_end.isoformat() if isinstance(current_period_end, datetime) else "",
            "billing_trial_end": trial_end.isoformat() if isinstance(trial_end, datetime) else "",
        }

    for key, val in values.items():
        await _upsert_user_setting(session, user=user, field_key=key, value=val)
    await session.commit()


def _fmt_ts(ts: datetime | None) -> str:
    if ts is None:
        return "Never"
    return ts.astimezone(_PACIFIC).strftime("%Y-%m-%d %H:%M PT")


def _freshness_status(ts: datetime | None, stale_after_hours: int) -> str:
    if ts is None:
        return "No activity"
    age_hours = (datetime.now(UTC) - ts.astimezone(UTC)).total_seconds() / 3600
    return "Healthy" if age_hours <= stale_after_hours else "Stale"


async def _proxyon_remaining_gb(timeout_seconds: float = 8.0) -> str | None:
    """Return residential GB remaining from ProxyOn API if credentials are configured."""
    api_key = (settings.proxyon_api_key or "").strip()
    if not api_key:
        return None

    timeout = httpx.Timeout(timeout_seconds)
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True, trust_env=False) as client:
            auth = await client.post(
                "https://api.proxyon.io/v1/auth/token",
                data={"apikey": api_key},
                headers={"Accept": "application/json"},
            )
            auth.raise_for_status()
            auth_body = auth.json()
            if not auth_body.get("success"):
                return None
            token = (auth_body.get("result") or {}).get("token")
            if not token:
                return None

            stats = await client.get(
                "https://api.proxyon.io/v1/residential/stats",
                headers={"X-Session-Token": token, "Accept": "application/json"},
            )
            stats.raise_for_status()
            stats_body = stats.json()
            if not stats_body.get("success"):
                return None
            result = stats_body.get("result") or {}

            for key in ("remaining_gb", "gb_remaining", "left_gb", "remaining", "traffic_left_gb"):
                if key in result and result[key] is not None:
                    return f"{float(result[key]):,.2f} GB"

            for key in ("total_gb", "used_gb"):
                if key in result and result[key] is not None:
                    total = float(result.get("total_gb") or 0)
                    used = float(result.get("used_gb") or 0)
                    if total > 0:
                        return f"{max(total - used, 0):,.2f} GB"
    except Exception:
        return None
    return None


async def _proxyon_residential_snapshot(timeout_seconds: float = 8.0) -> dict[str, Any]:
    """Return cached (hourly) ProxyOn residential connection state and remaining GB."""
    now_monotonic = time.monotonic()
    cached_age = now_monotonic - float(_proxyon_status_cache.get("fetched_monotonic") or 0.0)
    if cached_age < _PROXYON_STATUS_CACHE_TTL_SECONDS:
        return dict(_proxyon_status_cache)

    async with _proxyon_status_lock:
        now_monotonic = time.monotonic()
        cached_age = now_monotonic - float(_proxyon_status_cache.get("fetched_monotonic") or 0.0)
        if cached_age < _PROXYON_STATUS_CACHE_TTL_SECONDS:
            return dict(_proxyon_status_cache)

        checked_at = datetime.now(UTC)
        api_key = (settings.proxyon_api_key or "").strip()
        if not api_key:
            _proxyon_status_cache.update(
                {
                    "fetched_monotonic": now_monotonic,
                    "status_label": "Not Configured",
                    "connected": False,
                    "remaining_gb": None,
                    "expected_days_left": None,
                    "account_balance_usd": None,
                    "active_subscription_id": None,
                    "datacenter_count_live": None,
                    "datacenter_by_country": None,
                    "checked_at": None,
                }
            )
            return dict(_proxyon_status_cache)

        account_balance_usd: str | None = None
        data_left_gb: float | None = None
        expected_days_left: float | None = None
        active_sub_id: int | None = None
        dc_count_live: int | None = None
        dc_by_country: dict[str, int] | None = None
        connected = False
        status_label = "API Key Invalid"
        timeout = httpx.Timeout(timeout_seconds)
        try:
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=True, trust_env=False) as client:
                auth = await client.post(
                    "https://api.proxyon.io/v1/auth/token",
                    data={"apikey": api_key},
                    headers={"Accept": "application/json"},
                )
                auth.raise_for_status()
                auth_body = auth.json()
                token: str | None = None
                if auth_body.get("success"):
                    token = ((auth_body.get("result") or {}).get("token")
                             or (auth_body.get("result") or {}).get("sessionToken"))
                if token:
                    hdrs = {"X-Session-Token": token, "Accept": "application/json"}
                    # Account balance (USD) — same endpoint as before
                    acct = await client.get(
                        "https://api.proxyon.io/v1/account/info", headers=hdrs,
                    )
                    acct.raise_for_status()
                    acct_body = acct.json()
                    if acct_body.get("success"):
                        connected = True
                        balance = (acct_body.get("result") or {}).get("balance")
                        if balance is not None:
                            account_balance_usd = f"${float(balance):,.2f}"

                    # Residential subscription list — this is the authoritative
                    # "are credentials provisioned" signal. Creds come from the
                    # API (user+password returned per subscription), so API-key
                    # presence + an active subscription means we're configured.
                    # Note: /list does NOT return dataLeft; we fetch it via
                    # /residential/{id}/info for the active subscription.
                    subs = await client.get(
                        "https://api.proxyon.io/v1/residential/list", headers=hdrs,
                    )
                    subs.raise_for_status()
                    subs_body = subs.json()
                    sub_list: list = []
                    if subs_body.get("success"):
                        result = subs_body.get("result") or {}
                        if isinstance(result, list):
                            sub_list = result
                        elif isinstance(result, dict):
                            sub_list = (result.get("subscriptions")
                                        or result.get("list")
                                        or [])

                    if sub_list:
                        # Pick the main sub if tagged, else first entry
                        active = next(
                            (s for s in sub_list
                             if isinstance(s, dict) and s.get("isMain")),
                            sub_list[0] if isinstance(sub_list[0], dict) else None,
                        )
                        if isinstance(active, dict):
                            active_sub_id = active.get("id")

                        # Second API call: /info endpoint has the usage data
                        if active_sub_id is not None:
                            try:
                                info = await client.get(
                                    f"https://api.proxyon.io/v1/residential/{active_sub_id}/info",
                                    headers=hdrs,
                                )
                                info.raise_for_status()
                                info_body = info.json()
                                if info_body.get("success"):
                                    info_result = info_body.get("result") or {}
                                    # ProxyOn returns dataLeft in megabytes
                                    # (confirmed against live account with
                                    # expectedDaysLeft cross-check). Convert to GB.
                                    _left_mb = info_result.get("dataLeft")
                                    if _left_mb is not None:
                                        try:
                                            data_left_gb = float(_left_mb) / 1024.0
                                        except (TypeError, ValueError):
                                            data_left_gb = None
                                    _days = info_result.get("expectedDaysLeft")
                                    if _days is not None:
                                        try:
                                            expected_days_left = float(_days)
                                        except (TypeError, ValueError):
                                            expected_days_left = None
                            except Exception:
                                pass

                        status_label = (
                            "Active" if data_left_gb and data_left_gb > 0
                            else "Configured (No Data Left)" if data_left_gb == 0
                            else "Configured"  # has sub, data unknown (info call failed)
                        )
                    else:
                        status_label = "Configured (No Subscription)"

                    # Datacenter proxies — live count from /datacenter/list.
                    # Env-var PROXYON_DATACENTER_PROXIES is a comma-separated
                    # list of pre-wired connection strings the scraper uses at
                    # runtime; the live list is the authoritative inventory.
                    try:
                        dc = await client.get(
                            "https://api.proxyon.io/v1/datacenter/list", headers=hdrs,
                        )
                        dc.raise_for_status()
                        dc_body = dc.json()
                        if dc_body.get("success"):
                            dc_result = dc_body.get("result") or {}
                            if isinstance(dc_result, dict):
                                proxies = dc_result.get("proxies") or dc_result.get("list") or []
                            elif isinstance(dc_result, list):
                                proxies = dc_result
                            else:
                                proxies = []
                            active = [p for p in proxies
                                      if isinstance(p, dict)
                                      and (p.get("status") or "").lower() == "active"]
                            dc_count_live = len(active)
                            by_country: dict[str, int] = {}
                            for p in active:
                                cc = (p.get("country") or "??").lower()
                                by_country[cc] = by_country.get(cc, 0) + 1
                            dc_by_country = by_country or None
                    except Exception:
                        pass
        except Exception:
            connected = False
            status_label = "API Error"

        _proxyon_status_cache.update(
            {
                "fetched_monotonic": now_monotonic,
                "status_label": status_label,
                "connected": connected,
                "remaining_gb": (
                    f"{data_left_gb:.2f} GB" if data_left_gb is not None else None
                ),
                "expected_days_left": expected_days_left,
                "account_balance_usd": account_balance_usd,
                "active_subscription_id": active_sub_id,
                "datacenter_count_live": dc_count_live,
                "datacenter_by_country": dc_by_country,
                "checked_at": checked_at,
            }
        )
        return dict(_proxyon_status_cache)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/", response_class=HTMLResponse)
async def root() -> RedirectResponse:
    return RedirectResponse(url="/deals")


@router.get("/splash", response_class=HTMLResponse)
async def splash(request: Request, session: DBSession) -> HTMLResponse:
    users = list((await session.execute(select(User).order_by(User.name))).scalars())
    return templates.TemplateResponse(request, "splash.html", {"users": users})



@router.get("/settings/scraping-services", response_class=HTMLResponse)
async def settings_scraping_services(
    request: Request,
    session: DBSession,
) -> HTMLResponse:
    user = await _get_user(session, request)
    _require_settings_owner(user)
    dedup_count, conflicts_count = await _get_counts(session)
    address_issues_count = await _get_address_issues_count(session)

    crexi_job = (await session.execute(
        select(IngestJob)
        .where(IngestJob.source == "crexi")
        .order_by(IngestJob.started_at.desc())
        .limit(1)
    )).scalar_one_or_none()

    residential_username = (settings.proxyon_residential_username or "").strip()
    residential_password = (settings.proxyon_residential_password or "").strip()
    residential_env_creds = bool(residential_username and residential_password)
    datacenter_env_count = len([p for p in (settings.proxyon_datacenter_proxies or "").split(",") if p.strip()])
    proxyon_snapshot = await _proxyon_residential_snapshot()

    # Authoritative status = live API state. Residential creds are provisioned
    # via the ProxyOn API (GET /residential/list returns user+password per
    # subscription), so API-key presence + an active subscription means we
    # have usable credentials regardless of what's in the env vars.
    residential_status = proxyon_snapshot.get("status_label") or "Not Configured"
    residential_gb_remaining = proxyon_snapshot.get("remaining_gb")
    residential_balance = proxyon_snapshot.get("account_balance_usd")
    residential_sub_id = proxyon_snapshot.get("active_subscription_id")
    residential_days_left = proxyon_snapshot.get("expected_days_left")
    datacenter_count_live = proxyon_snapshot.get("datacenter_count_live")
    datacenter_by_country = proxyon_snapshot.get("datacenter_by_country") or {}
    # Prefer live count from API; fall back to env-var count if API unavailable
    datacenter_count = (
        datacenter_count_live
        if datacenter_count_live is not None
        else datacenter_env_count
    )
    # A residential subscription exists (live signal from API, not env-var peek)
    residential_configured = bool(residential_sub_id) or residential_env_creds
    _checked_at = proxyon_snapshot.get("checked_at")
    residential_last_checked = _fmt_ts(_checked_at) if _checked_at else "API key not configured"

    services = [
        {
            "name": "Crexi Ingest",
            "description": "Daily Crexi crawler run for refreshed multifamily listing coverage.",
            "status": _freshness_status(crexi_job.started_at if crexi_job else None, stale_after_hours=30),
            "schedule": "Daily at 06:00 PT via Celery beat",
            "proxy": "Residential (ProxyOn)" if residential_configured else "Residential (ProxyOn, not configured)",
            "last_run": _fmt_ts(crexi_job.started_at if crexi_job else None),
            "last_result": crexi_job.status if crexi_job else "never",
        },
        {
            "name": "Oregon eLicense",
            "description": "Monthly enrichment of broker license records (license type, status, personal address, affiliated firm, disciplinary actions) from the Oregon Real Estate Agency public lookup.",
            "status": "Pending Implementation",
            "schedule": "Monthly on the 2nd at 05:00 UTC via Celery beat",
            "proxy": "Residential (ProxyOn)" if residential_configured else "Residential (ProxyOn, not configured)",
            "last_run": "—",
            "last_result": "—",
            "action_url": "/scraper/oregon-elicense/run",
            "action_label": "Trigger Sweep",
            "action_method": "post",
        },
    ]

    return templates.TemplateResponse(
        request,
        "settings_scraping_services.html",
        {
            "services": services,
            "residential_status": residential_status,
            "datacenter_count": datacenter_count,
            "datacenter_count_live": datacenter_count_live,
            "datacenter_env_count": datacenter_env_count,
            "datacenter_by_country": datacenter_by_country,
            "residential_gb_remaining": residential_gb_remaining,
            "residential_balance": residential_balance,
            "residential_sub_id": residential_sub_id,
            "residential_days_left": residential_days_left,
            "residential_last_checked": residential_last_checked,
            **_base_ctx(user, dedup_count, "", address_issues_count, conflicts_count=conflicts_count),
        },
    )


# ---------------------------------------------------------------------------
# GET /settings/organization
# ---------------------------------------------------------------------------

@router.get("/settings/organization", response_class=HTMLResponse)
async def settings_organization(
    request: Request,
    session: DBSession,
) -> HTMLResponse:
    user = await _get_user(session, request)
    if user is None:
        return RedirectResponse(url="/login?next=/settings/organization", status_code=303)
    dedup_count, conflicts_count = await _get_counts(session)
    address_issues_count = await _get_address_issues_count(session)

    org = await session.get(Organization, user.org_id)
    org_users = list(
        (
            await session.execute(
                select(User).where(User.org_id == user.org_id).order_by(User.created_at)
            )
        ).scalars()
    )

    from app.models.org import OrgInvite as _OrgInviteQ
    pending_invites = (
        await session.execute(
            select(_OrgInviteQ).where(
                _OrgInviteQ.org_id == user.org_id,
                _OrgInviteQ.accepted_at.is_(None),
                _OrgInviteQ.expires_at > datetime.now(UTC),
            ).order_by(_OrgInviteQ.created_at.desc())
        )
    ).scalars().all()

    from app.models.settings import OrgSetting as _OrgSetting
    from app.settings.defaults import ORG_SET_FIELDS as _ORG_SET_FIELDS
    from app.settings.resolver import resolve_all_defaults as _resolve_all

    resolved = await _resolve_all(user.id, user.org_id, session)
    _org_rows = (
        await session.execute(select(_OrgSetting).where(_OrgSetting.org_id == user.org_id))
    ).scalars().all()
    org_settings_map = {
        r.field_key: {"value": r.value, "user_overridable": r.user_overridable}
        for r in _org_rows
    }

    from app.models.source_vehicle import SourceVehicle as _OSV_org
    org_source_vehicles = (
        await session.execute(
            select(_OSV_org).where(
                _OSV_org.scope == "org", _OSV_org.owner_id == user.org_id
            ).order_by(_OSV_org.label)
        )
    ).scalars().all()

    from app.models.settings import OrgDealTypeDefault as _OrgDTD
    from app.settings.resolver import resolve_timeline_defaults as _resolve_tl_org
    timeline_defaults_map = await _resolve_tl_org(user.id, user.org_id, session)
    _org_tl_rows = (
        await session.execute(select(_OrgDTD).where(_OrgDTD.org_id == user.org_id))
    ).scalars().all()
    org_timeline_map = {
        (r.deal_type, r.milestone_type): {
            "included": r.included,
            "duration_days": int(r.duration_days) if r.duration_days is not None else None,
            "starts_after_type": r.starts_after_type,
            "offset_days": int(r.offset_days),
            "user_overridable": r.user_overridable,
        }
        for r in _org_tl_rows
    }

    from app.models.scenario_template import ScenarioTemplate as _ST_org
    org_templates = list((await session.execute(
        select(_ST_org)
        .where(_ST_org.org_id == user.org_id)
        .order_by(_ST_org.created_at.desc())
    )).scalars())
    org_default_template_id = str(org.default_template_id) if org and org.default_template_id else None
    user_default_template_id = str(user.default_template_id) if user.default_template_id else None

    return templates.TemplateResponse(
        request,
        "settings_organization.html",
        {
            "org": org,
            "org_users": org_users,
            "pending_invites": pending_invites,
            "user": user,
            "resolved": resolved,
            "org_settings_map": org_settings_map,
            "org_set_fields": _ORG_SET_FIELDS,
            "org_source_vehicles": org_source_vehicles,
            "timeline_defaults_map": timeline_defaults_map,
            "org_timeline_map": org_timeline_map,
            "org_templates": org_templates,
            "org_default_template_id": org_default_template_id,
            "user_default_template_id": user_default_template_id,
            **_base_ctx(user, dedup_count, "", address_issues_count, conflicts_count=conflicts_count),
        },
    )


@router.post("/settings/organization", response_class=HTMLResponse)
async def settings_organization_post(
    request: Request,
    session: DBSession,
    org_name: str = Form(...),
    org_slug: str = Form(None),
) -> HTMLResponse:
    user = await _get_user(session, request)
    if user is None:
        return RedirectResponse(url="/login?next=/settings/organization", status_code=303)
    if not getattr(user, "is_org_admin", False):
        return HTMLResponse("Access denied", status_code=403)

    org = await session.get(Organization, user.org_id)
    if org is None:
        return HTMLResponse("Organization not found", status_code=404)

    org.name = org_name.strip()
    if org_slug and org_slug.strip():
        org.slug = org_slug.strip().lower().replace(" ", "-")
    await session.commit()

    # Redirect back to GET to show updated data
    return RedirectResponse(url="/settings/organization", status_code=303)


# ---------------------------------------------------------------------------
# GET /settings/org — org-wide underwriting defaults (admin only)
# ---------------------------------------------------------------------------


@router.get("/settings/org", response_class=HTMLResponse)
async def settings_org_defaults(request: Request) -> HTMLResponse:
    return RedirectResponse(url="/settings/organization", status_code=301)


# ---------------------------------------------------------------------------
# GET /settings/preferences — per-user underwriting preferences
# ---------------------------------------------------------------------------


@router.get("/settings/preferences", response_class=HTMLResponse)
async def settings_user_preferences(
    request: Request,
    session: DBSession,
) -> HTMLResponse:
    from app.models.settings import OrgSetting as _OrgSetting
    from app.models.settings import UserSetting as _UserSetting
    from app.settings.defaults import ORG_SET_FIELDS as _ORG_SET_FIELDS
    from app.settings.resolver import build_overridable_map as _build_overridable_map
    from app.settings.resolver import resolve_all_defaults as _resolve_all

    user = await _get_user(session, request)
    if user is None:
        return RedirectResponse(url="/login?next=/settings/preferences", status_code=303)

    dedup_count, conflicts_count = await _get_counts(session)
    address_issues_count = await _get_address_issues_count(session)
    resolved = await _resolve_all(user.id, user.org_id, session)

    _org_rows = (
        await session.execute(select(_OrgSetting).where(_OrgSetting.org_id == user.org_id))
    ).scalars().all()
    _user_rows = (
        await session.execute(select(_UserSetting).where(_UserSetting.user_id == user.id))
    ).scalars().all()
    overridable = _build_overridable_map(_org_rows)
    user_values = {r.field_key: r.value for r in _user_rows}

    from app.models.settings import UserDealTypeDefault as _UserDTD
    from app.settings.resolver import resolve_timeline_defaults as _resolve_tl2

    timeline_defaults_map = await _resolve_tl2(user.id, user.org_id, session)
    _user_dtd_rows = (
        await session.execute(select(_UserDTD).where(_UserDTD.user_id == user.id))
    ).scalars().all()
    user_timeline_map = {
        (r.deal_type, r.milestone_type): {
            "included": r.included,
            "duration_days": int(r.duration_days) if r.duration_days is not None else None,
            "starts_after_type": r.starts_after_type,
            "offset_days": int(r.offset_days),
        }
        for r in _user_dtd_rows
    }
    from app.models.settings import OrgDealTypeDefault as _OrgDTD2
    _org_dtd_rows2 = (
        await session.execute(select(_OrgDTD2).where(_OrgDTD2.org_id == user.org_id))
    ).scalars().all()
    timeline_overridable = {
        (r.deal_type, r.milestone_type): r.user_overridable for r in _org_dtd_rows2
    }

    from app.models.source_vehicle import SourceVehicle as _SV_usr
    org_source_vehicles_usr = (
        await session.execute(
            select(_SV_usr).where(
                _SV_usr.scope == "org", _SV_usr.owner_id == user.org_id
            ).order_by(_SV_usr.label)
        )
    ).scalars().all()
    user_source_vehicles = (
        await session.execute(
            select(_SV_usr).where(
                _SV_usr.scope == "user", _SV_usr.owner_id == user.id
            ).order_by(_SV_usr.label)
        )
    ).scalars().all()

    return templates.TemplateResponse(
        request,
        "settings_user.html",
        {
            "user": user,
            "resolved": resolved,
            "overridable": overridable,
            "user_values": user_values,
            "org_set_fields": _ORG_SET_FIELDS,
            "timeline_defaults_map": timeline_defaults_map,
            "user_timeline_map": user_timeline_map,
            "timeline_overridable": timeline_overridable,
            "org_source_vehicles": org_source_vehicles_usr,
            "user_source_vehicles": user_source_vehicles,
            **_base_ctx(user, dedup_count, "", address_issues_count, conflicts_count=conflicts_count),
        },
    )


@router.get("/settings/billing", response_class=HTMLResponse)
async def settings_billing(
    request: Request,
    session: DBSession,
    stripe: str = Query(default=""),
    err: str = Query(default=""),
) -> HTMLResponse:
    user = await _get_user(session, request)
    if user is None:
        return RedirectResponse(url="/login?next=/settings/billing", status_code=303)

    dedup_count, conflicts_count = await _get_counts(session)
    address_issues_count = await _get_address_issues_count(session)

    stripe_configured = _stripe_is_configured()
    stripe_embedded_ready = stripe_configured and bool(_stripe_publishable_key())
    stripe_test_mode = _stripe_secret_key().startswith("sk_test_") if stripe_configured else False
    customer_id = await _get_stripe_customer_id(session, user.id) if stripe_configured else None
    price_catalog = _stripe_price_catalog()

    cards: list[dict[str, str]] = []
    cards_error: str | None = None
    if stripe_configured and customer_id:
        try:
            cards = await _list_stripe_payment_methods(customer_id)
        except HTTPException as exc:
            cards_error = str(exc.detail)

    subscription: dict[str, Any] | None = None
    subscription_error: str | None = None
    if stripe_configured and customer_id:
        try:
            subscription = await _get_stripe_subscription_summary(customer_id)
            await _sync_user_billing_snapshot(session, user=user, subscription=subscription)
        except HTTPException as exc:
            subscription_error = str(exc.detail)
    else:
        await _sync_user_billing_snapshot(session, user=user, subscription=None)

    return templates.TemplateResponse(
        request,
        "settings_billing.html",
        {
            "stripe_configured": stripe_configured,
            "stripe_embedded_ready": stripe_embedded_ready,
            "stripe_test_mode": stripe_test_mode,
            "stripe_publishable_key": _stripe_publishable_key(),
            "stripe_customer_id": customer_id,
            "stripe_price_pro_monthly": price_catalog.get("pro_monthly") or "",
            "stripe_price_pro_annual": price_catalog.get("pro_annual") or "",
            "stripe_trial_days": max(int(settings.stripe_trial_days or 0), 0),
            "cards": cards,
            "cards_error": cards_error,
            "subscription": subscription,
            "subscription_error": subscription_error,
            "stripe_state": stripe,
            "stripe_state_message": _stripe_state_message(stripe),
            "stripe_error_detail": (err or "").strip(),
            **_base_ctx(user, dedup_count, "", address_issues_count, conflicts_count=conflicts_count),
        },
    )


@router.post("/settings/billing/stripe/embedded-session", response_class=JSONResponse)
async def settings_billing_embedded_session(
    request: Request,
    session: DBSession,
) -> JSONResponse:
    user = await _get_user(session, request)
    if user is None:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    if not _stripe_is_configured() or not _stripe_publishable_key():
        return JSONResponse({"error": "Stripe keys are not configured"}, status_code=400)

    try:
        body = await request.json()
    except Exception:
        body = {}
    intent = str((body or {}).get("intent") or "setup").strip().lower()

    customer_id = await _ensure_stripe_customer_id(session, user)
    price_catalog = _stripe_price_catalog()

    payload: list[tuple[str, str]]
    if intent == "setup":
        payload = [
            ("mode", "setup"),
            ("ui_mode", "embedded_page"),
            ("customer", customer_id),
            ("payment_method_types[]", "card"),
            ("billing_address_collection", "auto"),
            ("return_url", f"{settings.app_base_url}/settings/billing?stripe=success"),
        ]
    elif intent in {"subscribe_pro_monthly", "subscribe_pro_annual"}:
        tier_key = "pro_monthly" if intent == "subscribe_pro_monthly" else "pro_annual"
        price_id = (price_catalog.get(tier_key) or "").strip()
        if not price_id:
            return JSONResponse({"error": f"Stripe price for {tier_key} is not configured"}, status_code=400)
        trial_days = max(int(settings.stripe_trial_days or 0), 0)
        payload = [
            ("mode", "subscription"),
            ("ui_mode", "embedded_page"),
            ("customer", customer_id),
            ("line_items[0][price]", price_id),
            ("line_items[0][quantity]", "1"),
            ("allow_promotion_codes", "true"),
            ("return_url", f"{settings.app_base_url}/settings/billing?stripe=success"),
        ]
        if trial_days > 0:
            payload.append(("subscription_data[trial_period_days]", str(trial_days)))
    else:
        return JSONResponse({"error": "Unsupported Stripe intent"}, status_code=400)

    try:
        checkout = await _stripe_api_request(
            "POST",
            "/v1/checkout/sessions",
            data=payload,
        )
    except HTTPException as exc:
        detail = str(exc.detail or "")
        if "No such customer" in detail or "resource_missing" in detail:
            try:
                await _clear_stripe_customer_id(session, user.id)
                customer_id = await _ensure_stripe_customer_id(session, user)
                remapped = [(k, customer_id if k == "customer" else v) for k, v in payload]
                checkout = await _stripe_api_request(
                    "POST",
                    "/v1/checkout/sessions",
                    data=remapped,
                )
            except HTTPException as retry_exc:
                return JSONResponse({"error": str(retry_exc.detail or "Stripe error")}, status_code=502)
        else:
            return JSONResponse({"error": detail or "Stripe error"}, status_code=502)

    client_secret = str(checkout.get("client_secret") or "").strip()
    if not client_secret:
        return JSONResponse({"error": "Stripe did not return an embedded client_secret"}, status_code=502)

    return JSONResponse({"clientSecret": client_secret, "intent": intent})


@router.post("/settings/billing/stripe/subscription/cancel", response_class=HTMLResponse)
async def settings_billing_cancel_subscription(
    request: Request,
    session: DBSession,
) -> HTMLResponse:
    user = await _get_user(session, request)
    if user is None:
        return RedirectResponse(url="/login?next=/settings/billing", status_code=303)

    if not _stripe_is_configured():
        return RedirectResponse(url="/settings/billing?stripe=config-missing", status_code=303)

    customer_id = await _get_stripe_customer_id(session, user.id)
    if not customer_id:
        return RedirectResponse(url="/settings/billing?stripe=no-subscription", status_code=303)

    summary = await _get_stripe_subscription_summary(customer_id)
    if not summary:
        return RedirectResponse(url="/settings/billing?stripe=no-subscription", status_code=303)
    if summary.get("status") == "canceled":
        return RedirectResponse(url="/settings/billing?stripe=already-cancelled", status_code=303)

    await _stripe_api_request(
        "POST",
        f"/v1/subscriptions/{summary['id']}",
        data=[("cancel_at_period_end", "true")],
    )
    return RedirectResponse(url="/settings/billing?stripe=cancel-scheduled", status_code=303)


@router.post("/settings/billing/stripe/subscription/reactivate", response_class=HTMLResponse)
async def settings_billing_reactivate_subscription(
    request: Request,
    session: DBSession,
) -> HTMLResponse:
    user = await _get_user(session, request)
    if user is None:
        return RedirectResponse(url="/login?next=/settings/billing", status_code=303)

    if not _stripe_is_configured():
        return RedirectResponse(url="/settings/billing?stripe=config-missing", status_code=303)

    customer_id = await _get_stripe_customer_id(session, user.id)
    if not customer_id:
        return RedirectResponse(url="/settings/billing?stripe=no-subscription", status_code=303)

    summary = await _get_stripe_subscription_summary(customer_id)
    if not summary:
        return RedirectResponse(url="/settings/billing?stripe=no-subscription", status_code=303)

    if summary.get("cancel_at_period_end"):
        await _stripe_api_request(
            "POST",
            f"/v1/subscriptions/{summary['id']}",
            data=[("cancel_at_period_end", "false")],
        )
        return RedirectResponse(url="/settings/billing?stripe=reactivated", status_code=303)
    return RedirectResponse(url="/settings/billing", status_code=303)


@router.post("/settings/billing/stripe/payment-method/default", response_class=HTMLResponse)
async def settings_billing_set_default_payment_method(
    request: Request,
    session: DBSession,
    payment_method_id: str = Form(...),
) -> HTMLResponse:
    user = await _get_user(session, request)
    if user is None:
        return RedirectResponse(url="/login?next=/settings/billing", status_code=303)

    if not _stripe_is_configured():
        return RedirectResponse(url="/settings/billing?stripe=config-missing", status_code=303)

    customer_id = await _get_stripe_customer_id(session, user.id)
    if not customer_id:
        return RedirectResponse(url="/settings/billing?stripe=no-subscription", status_code=303)

    pm_id = (payment_method_id or "").strip()
    if not pm_id:
        return RedirectResponse(url="/settings/billing?stripe=card-remove-error", status_code=303)

    await _stripe_api_request(
        "POST",
        f"/v1/customers/{customer_id}",
        data=[("invoice_settings[default_payment_method]", pm_id)],
    )
    return RedirectResponse(url="/settings/billing?stripe=card-default-updated", status_code=303)


@router.post("/settings/billing/stripe/payment-method/remove", response_class=HTMLResponse)
async def settings_billing_remove_payment_method(
    request: Request,
    session: DBSession,
    payment_method_id: str = Form(...),
) -> HTMLResponse:
    user = await _get_user(session, request)
    if user is None:
        return RedirectResponse(url="/login?next=/settings/billing", status_code=303)

    if not _stripe_is_configured():
        return RedirectResponse(url="/settings/billing?stripe=config-missing", status_code=303)

    customer_id = await _get_stripe_customer_id(session, user.id)
    if not customer_id:
        return RedirectResponse(url="/settings/billing?stripe=no-subscription", status_code=303)

    pm_id = (payment_method_id or "").strip()
    if not pm_id:
        return RedirectResponse(url="/settings/billing?stripe=card-remove-error", status_code=303)

    try:
        current_default = await _get_customer_default_payment_method(customer_id)
        await _stripe_api_request("POST", f"/v1/payment_methods/{pm_id}/detach")

        if current_default and current_default == pm_id:
            remaining = await _list_stripe_payment_methods(customer_id)
            fallback = next((c.get("id") for c in remaining if c.get("id")), None)
            if fallback:
                await _stripe_api_request(
                    "POST",
                    f"/v1/customers/{customer_id}",
                    data=[("invoice_settings[default_payment_method]", str(fallback))],
                )
    except HTTPException:
        return RedirectResponse(url="/settings/billing?stripe=card-remove-error", status_code=303)

    return RedirectResponse(url="/settings/billing?stripe=card-removed", status_code=303)


@router.post("/settings/billing/stripe/setup-session", response_class=HTMLResponse)
async def settings_billing_create_setup_session(
    request: Request,
    session: DBSession,
) -> HTMLResponse:
    user = await _get_user(session, request)
    if user is None:
        return RedirectResponse(url="/login?next=/settings/billing", status_code=303)

    if not _stripe_is_configured():
        return RedirectResponse(url="/settings/billing?stripe=config-missing", status_code=303)

    def _checkout_payload(customer_id: str) -> list[tuple[str, str]]:
        return [
            ("mode", "setup"),
            ("customer", customer_id),
            ("payment_method_types[]", "card"),
            ("billing_address_collection", "auto"),
            ("success_url", f"{settings.app_base_url}/settings/billing?stripe=success"),
            ("cancel_url", f"{settings.app_base_url}/settings/billing?stripe=cancel"),
        ]

    try:
        customer_id = await _ensure_stripe_customer_id(session, user)
        checkout = await _stripe_api_request(
            "POST",
            "/v1/checkout/sessions",
            data=_checkout_payload(customer_id),
        )
    except HTTPException as exc:
        detail = str(exc.detail or "")
        if "No such customer" in detail or "resource_missing" in detail:
            try:
                await _clear_stripe_customer_id(session, user.id)
                customer_id = await _ensure_stripe_customer_id(session, user)
                checkout = await _stripe_api_request(
                    "POST",
                    "/v1/checkout/sessions",
                    data=_checkout_payload(customer_id),
                )
            except HTTPException as retry_exc:
                retry_detail = quote_plus(str(retry_exc.detail or "")[:240])
                return RedirectResponse(
                    url=f"/settings/billing?stripe=error&err={retry_detail}",
                    status_code=303,
                )
        else:
            safe_detail = quote_plus(detail[:240])
            return RedirectResponse(
                url=f"/settings/billing?stripe=error&err={safe_detail}",
                status_code=303,
            )

    checkout_url = str(checkout.get("url") or "").strip()
    if not checkout_url:
        return RedirectResponse(url="/settings/billing?stripe=error", status_code=303)
    return RedirectResponse(url=checkout_url, status_code=303)


@router.get("/mock/billing/embedded", response_class=HTMLResponse)
async def billing_embedded_mock_page(
    request: Request,
    session: DBSession,
    state: str = Query(default=""),
) -> HTMLResponse:
    user = await _get_user(session, request)
    if user is None:
        return RedirectResponse(url="/login?next=/mock/billing/embedded", status_code=303)

    dedup_count, conflicts_count = await _get_counts(session)
    address_issues_count = await _get_address_issues_count(session)

    stripe_configured = _stripe_is_configured() and bool(_stripe_publishable_key())
    return templates.TemplateResponse(
        request,
        "billing_embedded_mock.html",
        {
            "stripe_configured": stripe_configured,
            "stripe_publishable_key": _stripe_publishable_key(),
            "state": state,
            **_base_ctx(user, dedup_count, "", address_issues_count, conflicts_count=conflicts_count),
        },
    )


@router.post("/mock/billing/embedded/session", response_class=JSONResponse)
async def billing_embedded_mock_create_session(
    request: Request,
    session: DBSession,
) -> JSONResponse:
    user = await _get_user(session, request)
    if user is None:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    if not _stripe_is_configured() or not _stripe_publishable_key():
        return JSONResponse({"error": "Stripe keys are not configured"}, status_code=400)

    def _embedded_payload(customer_id: str) -> list[tuple[str, str]]:
        return [
            ("mode", "setup"),
            ("ui_mode", "embedded_page"),
            ("customer", customer_id),
            ("payment_method_types[]", "card"),
            ("billing_address_collection", "auto"),
            ("return_url", f"{settings.app_base_url}/mock/billing/embedded?state=complete"),
        ]

    try:
        customer_id = await _ensure_stripe_customer_id(session, user)
        checkout = await _stripe_api_request(
            "POST",
            "/v1/checkout/sessions",
            data=_embedded_payload(customer_id),
        )
    except HTTPException as exc:
        detail = str(exc.detail or "")
        if "No such customer" in detail or "resource_missing" in detail:
            try:
                await _clear_stripe_customer_id(session, user.id)
                customer_id = await _ensure_stripe_customer_id(session, user)
                checkout = await _stripe_api_request(
                    "POST",
                    "/v1/checkout/sessions",
                    data=_embedded_payload(customer_id),
                )
            except HTTPException as retry_exc:
                return JSONResponse({"error": str(retry_exc.detail or "Stripe error")}, status_code=502)
        else:
            return JSONResponse({"error": detail or "Stripe error"}, status_code=502)

    client_secret = str(checkout.get("client_secret") or "").strip()
    if not client_secret:
        return JSONResponse({"error": "Stripe did not return an embedded client_secret"}, status_code=502)
    return JSONResponse({"clientSecret": client_secret})


@router.post("/ui/admin/backfill-listing-buckets")
async def admin_backfill_listing_buckets(
    session: DBSession,
) -> JSONResponse:
    """Classify all ScrapedListings that have no priority_bucket yet,
    using the listing's own zoning / county / jurisdiction fields."""
    from app.utils.priority import classify as _classify

    stmt = (
        select(ScrapedListing)
        .where(ScrapedListing.priority_bucket.is_(None))
        .options(selectinload(ScrapedListing.broker))
    )
    listings = list((await session.execute(stmt)).scalars())
    updated = 0
    for listing in listings:
        bucket = _classify(
            zoning_code=listing.zoning,
            zoning_description=None,
            county=listing.county,
            jurisdiction=listing.city,
            current_use=None,
            property_type=listing.property_type,
        )
        listing.priority_bucket = bucket.value
        updated += 1

    await session.commit()
    return JSONResponse({"updated": updated})





# ---------------------------------------------------------------------------
# Vehicle-settings form parsing helpers (used only by vehicle routes below)
# ---------------------------------------------------------------------------


def _fd(v: str | None) -> Decimal | None:
    """Parse an optional Decimal from a form field. Strips commas tolerantly."""
    if not v or not v.strip():
        return None
    try:
        return Decimal(v.strip().replace(",", ""))
    except Exception:
        return None


def _parse_vehicle_carry_schedule(form) -> dict | None:
    """Parse carry schedule arrays from a vehicle settings form into carry_config dict."""
    labels = form.getlist("v_carry_phase_label[]")
    types = form.getlist("v_carry_phase_type[]")
    dur_types = form.getlist("v_carry_phase_duration_type[]")
    months_vals = form.getlist("v_carry_phase_months[]")
    milestones = form.getlist("v_carry_phase_milestone_key[]")
    rates = form.getlist("v_carry_phase_rate_pct[]")
    amorts = form.getlist("v_carry_phase_amort_years[]")
    if not types:
        return None
    phases = []
    for i, ct in enumerate(types):
        ct = ct.strip()
        if not ct or ct == "none":
            continue
        dur_type = (dur_types[i] if i < len(dur_types) else "remainder").strip()
        if dur_type == "months":
            try:
                n = int(months_vals[i]) if i < len(months_vals) and months_vals[i].strip() else 0
            except ValueError:
                n = 0
            dur: dict = {"type": "months", "months": n}
        elif dur_type == "milestone":
            mk = (milestones[i] if i < len(milestones) else "").strip()
            dur = {"type": "milestone", "milestone_key": mk}
        else:
            dur = {"type": "remainder"}
        p: dict = {
            "label": (labels[i] if i < len(labels) else "").strip() or ct,
            "carry_type": ct,
            "duration": dur,
        }
        try:
            if i < len(rates) and rates[i].strip():
                p["rate_pct"] = float(rates[i].strip())
        except ValueError:
            pass
        try:
            if i < len(amorts) and amorts[i].strip():
                p["amort_term_years"] = int(amorts[i].strip())
        except ValueError:
            pass
        phases.append(p)
    return {"schedule": phases} if phases else None


def _parse_vehicle_fee_terms(form) -> dict:
    """Parse Developer Fee Rule fields from a vehicle settings form.

    Empty dict means preset imposes no Dev Fee cap. Persisted to
    ``SourceVehicle.fee_terms`` and inherited by CapitalModules created
    from this preset.
    """
    out: dict = {}
    if (_mp := _fd(form.get("fee_terms_max_pct"))) is not None:
        out["max_pct"] = float(_mp)
    if (_puc := _fd(form.get("fee_terms_per_unit_cap"))) is not None:
        out["per_unit_cap"] = float(_puc)
    if (_ac := _fd(form.get("fee_terms_absolute_cap"))) is not None:
        out["absolute_cap"] = float(_ac)
    _excl = [x.strip() for x in form.getlist("fee_terms_basis_exclusions[]") if x.strip()]
    if _excl:
        out["basis_exclusions"] = _excl
    if form.get("fee_terms_regulated") == "on":
        out["regulated"] = True
    if (_notes := (form.get("fee_terms_notes") or "").strip()):
        out["notes"] = _notes
    return out

# ---------------------------------------------------------------------------
# Source Vehicle management (Phase G)
# ---------------------------------------------------------------------------

# CANONICAL SOURCE VEHICLE TYPE LIST — keep in sync with ALL of:
# settings_user.html (_vt_labels)
# settings_organization.html (_vt_labels_org)
# app/templates/partials/model_builder_line_form.html (_ALL_TYPES)
# When adding a new VehicleType, update all four locations.
_VEHICLE_TYPE_LABELS = {
    "equity": "Equity",
    "debt": "Debt",
    "forgivable_loan": "Forgivable Loan",
    "grant": "Grant",
    "deferred_developer_fee": "Deferred Developer Fee",
    "float_earnings": "Float Earnings (T-Bond Yield)",
}


def _build_deferred_source_config(form: Any) -> dict:
    sc: dict = {}
    _raw_defer = form.get("defer_pct_of_dev_fee")
    if _raw_defer:
        sc["defer_pct_of_dev_fee"] = float(_raw_defer)
    _rel_keys = list(form.getlist("sv_rel_milestone_key[]"))
    _rel_weights = list(form.getlist("sv_rel_weight_pct[]"))
    _release = [
        {"milestone_key": k, "weight": float(w)}
        for k, w in zip(_rel_keys, _rel_weights)
        if k and w
    ]
    if _release:
        sc["release_schedule"] = _release
    return sc


@router.get("/settings/vehicles", response_class=HTMLResponse)
async def vehicle_settings_page(
    request: Request,
    session: DBSession,
) -> HTMLResponse:
    user = await _get_user(session, request)
    if user is None:
        return RedirectResponse(url="/login?next=/settings/vehicles", status_code=303)

    from app.models.source_vehicle import SourceVehicle as _SV_list
    dedup_count, conflicts_count = await _get_counts(session)
    address_issues_count = await _get_address_issues_count(session)

    org_vehicles = (
        await session.execute(
            select(_SV_list).where(
                _SV_list.scope == "org", _SV_list.owner_id == user.org_id
            ).order_by(_SV_list.vehicle_type, _SV_list.label)
        )
    ).scalars().all()

    user_vehicles = (
        await session.execute(
            select(_SV_list).where(
                _SV_list.scope == "user", _SV_list.owner_id == user.id
            ).order_by(_SV_list.vehicle_type, _SV_list.label)
        )
    ).scalars().all()

    return templates.TemplateResponse(
        request,
        "settings_vehicles.html",
        {
            "org_vehicles": org_vehicles,
            "user_vehicles": user_vehicles,
            "vehicle_type_labels": _VEHICLE_TYPE_LABELS,
            **_base_ctx(user, dedup_count, "", address_issues_count, conflicts_count=conflicts_count),
        },
    )


@router.get("/settings/vehicles/{vehicle_id}/form", response_class=HTMLResponse)
async def vehicle_edit_form(
    request: Request,
    vehicle_id: UUID,
    session: DBSession,
) -> HTMLResponse:
    user = await _get_user(session, request)
    if user is None:
        return HTMLResponse("Unauthorized", status_code=401)

    from app.models.source_vehicle import SourceVehicle as _SV_ef
    vehicle = (await session.execute(
        select(_SV_ef).where(
            _SV_ef.id == vehicle_id,
            (
                ((_SV_ef.scope == "org") & (_SV_ef.owner_id == user.org_id)) |
                ((_SV_ef.scope == "user") & (_SV_ef.owner_id == user.id))
            ),
        )
    )).scalar_one_or_none()
    if vehicle is None:
        return HTMLResponse("Vehicle not found", status_code=404)

    return templates.TemplateResponse(
        request,
        "partials/vehicle_form.html",
        {"vehicle": vehicle, "vehicle_type_labels": _VEHICLE_TYPE_LABELS},
    )


@router.post("/settings/vehicles", response_class=HTMLResponse)
async def vehicle_create(
    request: Request,
    session: DBSession,
) -> HTMLResponse:
    user = await _get_user(session, request)
    if user is None:
        return HTMLResponse("Unauthorized", status_code=401)

    form = await request.form()
    scope = str(form.get("scope", "org")).strip()
    label = str(form.get("label", "")).strip()
    vehicle_type = str(form.get("vehicle_type", "equity")).strip()
    equity_role = str(form.get("equity_role", "")).strip() or None

    if not label:
        return HTMLResponse("<p class='text-muted'>Label is required.</p>", status_code=400)
    if vehicle_type not in _VEHICLE_TYPE_LABELS:
        return HTMLResponse("<p class='text-muted'>Invalid vehicle type.</p>", status_code=400)
    if vehicle_type == "equity" and equity_role not in ("gp", "lp"):
        return HTMLResponse("<p class='text-muted'>Equity vehicles must have GP or LP role.</p>", status_code=400)
    if vehicle_type != "equity":
        equity_role = None

    owner_id = user.org_id if scope == "org" else user.id

    from app.models.source_vehicle import SourceVehicle as _SV_cr
    _v_carry_config = _parse_vehicle_carry_schedule(form)
    _v_fee_terms = _parse_vehicle_fee_terms(form)
    vehicle = _SV_cr(
        scope=scope,
        owner_id=owner_id,
        label=label,
        vehicle_type=vehicle_type,
        equity_role=equity_role,
        default_waterfall_position=int(form.get("default_waterfall_position") or 0),
        draw_cadence=str(form.get("draw_cadence", "monthly") or "monthly"),
        interest_rate_pct=form.get("interest_rate_pct") or None,
        carry_type=form.get("carry_type") or None,
        day_count_convention=str(form.get("day_count_convention", "actual_360") or "actual_360"),
        io_period_months=int(form.get("io_period_months")) if form.get("io_period_months") else None,
        amort_term_years=int(form.get("amort_term_years")) if form.get("amort_term_years") else None,
        pref_rate_pct=form.get("pref_rate_pct") or None,
        carry_config=_v_carry_config if _v_carry_config else None,
        fee_terms=_v_fee_terms,
        source_config=_build_deferred_source_config(form) if vehicle_type == "deferred_developer_fee" else None,
        created_by=user.id,
        updated_by=user.id,
    )
    session.add(vehicle)
    await session.commit()

    return RedirectResponse(url="/settings/vehicles", status_code=303)


@router.post("/settings/vehicles/{vehicle_id}", response_class=HTMLResponse)
async def vehicle_update(
    request: Request,
    vehicle_id: UUID,
    session: DBSession,
) -> HTMLResponse:
    user = await _get_user(session, request)
    if user is None:
        return HTMLResponse("Unauthorized", status_code=401)

    from app.models.source_vehicle import SourceVehicle as _SV_up
    vehicle = (await session.execute(
        select(_SV_up).where(
            _SV_up.id == vehicle_id,
            (
                ((_SV_up.scope == "org") & (_SV_up.owner_id == user.org_id)) |
                ((_SV_up.scope == "user") & (_SV_up.owner_id == user.id))
            ),
        )
    )).scalar_one_or_none()
    if vehicle is None:
        return HTMLResponse("Vehicle not found", status_code=404)

    form = await request.form()
    vehicle.label = str(form.get("label", vehicle.label)).strip()
    new_vt = str(form.get("vehicle_type", vehicle.vehicle_type)).strip()
    if new_vt in _VEHICLE_TYPE_LABELS:
        vehicle.vehicle_type = new_vt
    er = str(form.get("equity_role", "")).strip() or None
    vehicle.equity_role = er if vehicle.vehicle_type == "equity" else None
    vehicle.draw_cadence = str(form.get("draw_cadence", vehicle.draw_cadence) or vehicle.draw_cadence)
    vehicle.day_count_convention = str(form.get("day_count_convention", vehicle.day_count_convention) or "actual_360")
    vehicle.interest_rate_pct = form.get("interest_rate_pct") or None
    vehicle.carry_type = form.get("carry_type") or None
    vehicle.io_period_months = int(form.get("io_period_months")) if form.get("io_period_months") else None
    vehicle.amort_term_years = int(form.get("amort_term_years")) if form.get("amort_term_years") else None
    vehicle.pref_rate_pct = form.get("pref_rate_pct") or None
    vehicle.default_waterfall_position = int(form.get("default_waterfall_position") or vehicle.default_waterfall_position)
    _new_carry_config = _parse_vehicle_carry_schedule(form)
    vehicle.carry_config = _new_carry_config if _new_carry_config else vehicle.carry_config
    vehicle.fee_terms = _parse_vehicle_fee_terms(form)
    if vehicle.vehicle_type == "deferred_developer_fee":
        vehicle.source_config = _build_deferred_source_config(form)
    vehicle.updated_by = user.id
    await session.commit()

    # Propagate carry schedule to all CapitalModules using this vehicle.
    if _new_carry_config and _new_carry_config.get("schedule"):
        _linked_modules = (await session.execute(
            select(CapitalModule).where(CapitalModule.source_vehicle_id == vehicle_id)
        )).scalars().all()
        for _lm in _linked_modules:
            _lm_carry = dict(_lm.carry or {})
            if not _lm_carry.get("_schedule_override"):
                _lm_carry["schedule"] = _new_carry_config["schedule"]
                _lm.carry = _lm_carry
                session.add(_lm)
        if _linked_modules:
            await session.commit()

    return RedirectResponse(url="/settings/vehicles", status_code=303)


@router.delete("/settings/vehicles/{vehicle_id}", response_class=HTMLResponse)
async def vehicle_delete(
    request: Request,
    vehicle_id: UUID,
    session: DBSession,
) -> HTMLResponse:
    user = await _get_user(session, request)
    if user is None:
        return HTMLResponse("Unauthorized", status_code=401)

    from app.models.source_vehicle import SourceVehicle as _SV_del
    vehicle = (await session.execute(
        select(_SV_del).where(
            _SV_del.id == vehicle_id,
            (
                ((_SV_del.scope == "org") & (_SV_del.owner_id == user.org_id)) |
                ((_SV_del.scope == "user") & (_SV_del.owner_id == user.id))
            ),
        )
    )).scalar_one_or_none()
    if vehicle is None:
        return HTMLResponse("", status_code=404)

    await session.delete(vehicle)
    await session.commit()
    return HTMLResponse("")


# ── Scenario Templates ────────────────────────────────────────────────────────

@router.get("/ui/settings/scenario-templates", response_class=HTMLResponse)
async def scenario_templates_partial(
    request: Request,
    session: DBSession,
) -> HTMLResponse:
    """HTMX partial — template list for org settings page."""
    from app.models.scenario_template import ScenarioTemplate as _ST
    user = await _get_user(session, request)
    if user is None or user.org_id is None:
        return HTMLResponse("")
    org = await session.get(Organization, user.org_id)
    rows = list((await session.execute(
        select(_ST)
        .where(_ST.org_id == user.org_id)
        .order_by(_ST.created_at.desc())
    )).scalars())
    org_default = getattr(org, "default_template_id", None) if org else None
    user_default = getattr(user, "default_template_id", None)
    return templates.TemplateResponse(
        request, "partials/scenario_templates_list.html",
        {
            "templates": rows,
            "org_default_id": str(org_default) if org_default else None,
            "user_default_id": str(user_default) if user_default else None,
            "user": user,
        },
    )


@router.post("/ui/settings/scenario-templates/{template_id}/delete", response_class=HTMLResponse)
async def delete_scenario_template(
    request: Request,
    template_id: UUID,
    session: DBSession,
) -> HTMLResponse:
    from app.models.scenario_template import ScenarioTemplate as _ST
    user = await _get_user(session, request)
    if user is None or user.org_id is None:
        return HTMLResponse("", status_code=403)
    row = (await session.execute(
        select(_ST).where(_ST.id == template_id, _ST.org_id == user.org_id)
    )).scalar_one_or_none()
    if row is None:
        return HTMLResponse("", status_code=404)
    await session.delete(row)
    # Clear default pointers that referenced this template
    org = await session.get(Organization, user.org_id)
    if org and getattr(org, "default_template_id", None) == template_id:
        org.default_template_id = None
    users_with_default = list((await session.execute(
        select(User).where(User.org_id == user.org_id, User.default_template_id == template_id)
    )).scalars())
    for u in users_with_default:
        u.default_template_id = None
    await session.commit()
    return HTMLResponse("")


@router.post("/ui/settings/scenario-templates/{template_id}/set-org-default", response_class=HTMLResponse)
async def set_org_default_template(
    request: Request,
    template_id: UUID,
    session: DBSession,
) -> HTMLResponse:
    from app.models.scenario_template import ScenarioTemplate as _ST
    user = await _get_user(session, request)
    if user is None or user.org_id is None or not user.is_org_admin:
        return HTMLResponse("", status_code=403)
    row = (await session.execute(
        select(_ST).where(_ST.id == template_id, _ST.org_id == user.org_id)
    )).scalar_one_or_none()
    if row is None:
        return HTMLResponse("", status_code=404)
    org = await session.get(Organization, user.org_id)
    if org:
        org.default_template_id = template_id
    await session.commit()
    return HTMLResponse('<span class="badge badge-success">Set as org default</span>')


@router.post("/ui/settings/scenario-templates/{template_id}/set-user-default", response_class=HTMLResponse)
async def set_user_default_template(
    request: Request,
    template_id: UUID,
    session: DBSession,
) -> HTMLResponse:
    from app.models.scenario_template import ScenarioTemplate as _ST
    user = await _get_user(session, request)
    if user is None or user.org_id is None:
        return HTMLResponse("", status_code=403)
    row = (await session.execute(
        select(_ST).where(_ST.id == template_id, _ST.org_id == user.org_id)
    )).scalar_one_or_none()
    if row is None:
        return HTMLResponse("", status_code=404)
    user.default_template_id = template_id
    await session.commit()
    return HTMLResponse('<span class="badge badge-success">Set as your default</span>')


# ── Document Task Templates (org default tasks seeded onto new projects) ──────

async def _task_templates_response(request: Request, session: DBSession, user) -> HTMLResponse:
    from app.models.document import DocumentTaskTemplate as _TT
    rows = list((await session.execute(
        select(_TT)
        .where(_TT.org_id == user.org_id)
        .order_by(_TT.sort_order.asc(), _TT.created_at.asc())
    )).scalars())
    return templates.TemplateResponse(
        request, "partials/task_templates_list.html",
        {"task_templates": rows, "user": user},
    )


@router.get("/ui/settings/task-templates", response_class=HTMLResponse)
async def task_templates_partial(request: Request, session: DBSession) -> HTMLResponse:
    """HTMX partial — org default-task template list for the settings page."""
    user = await _get_user(session, request)
    if user is None or user.org_id is None:
        return HTMLResponse("")
    return await _task_templates_response(request, session, user)


@router.post("/ui/settings/task-templates", response_class=HTMLResponse)
async def create_task_template(
    request: Request, session: DBSession, title: str = Form(...)
) -> HTMLResponse:
    from app.models.document import DocumentTaskTemplate as _TT
    user = await _get_user(session, request)
    if user is None or user.org_id is None:
        return HTMLResponse("", status_code=403)
    title = (title or "").strip()
    if title:
        # New template sorts after existing ones.
        max_order = (await session.execute(
            select(func.coalesce(func.max(_TT.sort_order), 0)).where(_TT.org_id == user.org_id)
        )).scalar_one()
        session.add(_TT(org_id=user.org_id, title=title[:512], sort_order=int(max_order) + 1))
        await session.commit()
    return await _task_templates_response(request, session, user)


@router.post("/ui/settings/task-templates/{template_id}/delete", response_class=HTMLResponse)
async def delete_task_template(
    request: Request, template_id: UUID, session: DBSession
) -> HTMLResponse:
    from app.models.document import DocumentTaskTemplate as _TT
    user = await _get_user(session, request)
    if user is None or user.org_id is None:
        return HTMLResponse("", status_code=403)
    row = (await session.execute(
        select(_TT).where(_TT.id == template_id, _TT.org_id == user.org_id)
    )).scalar_one_or_none()
    if row is None:
        return HTMLResponse("", status_code=404)
    await session.delete(row)
    await session.commit()
    return await _task_templates_response(request, session, user)

