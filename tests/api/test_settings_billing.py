from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routers import ui
from app.api.auth import COOKIE_NAME, create_session_token
from app.config import settings
from app.models.settings import UserSetting
from tests.conftest import seed_org


pytestmark = pytest.mark.asyncio


async def _auth(client: AsyncClient, user_id) -> None:
    client.cookies.set(COOKIE_NAME, create_session_token(user_id))


async def test_billing_page_redirects_to_login_when_unauthenticated(
    client: AsyncClient,
) -> None:
    resp = await client.get("/settings/billing", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/login?next=/settings/billing"


async def test_billing_page_renders_for_authenticated_user(
    client: AsyncClient,
    session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "stripe_secret_key", "", raising=False)

    org, user = await seed_org(session)
    await session.commit()
    await _auth(client, user.id)

    resp = await client.get("/settings/billing")
    assert resp.status_code == 200
    assert "Billing" in resp.text
    assert "Stripe Not Fully Configured" in resp.text
    assert '<a href="/settings/billing" class="settings-popup-item">' not in resp.text


async def test_billing_menu_link_shows_for_stephen_ketch(
    client: AsyncClient,
    session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "stripe_secret_key", "", raising=False)

    org, user = await seed_org(session)
    user.name = "Stephen Ketch"
    user.email = "stephenjketch@gmail.com"
    session.add(user)
    await session.commit()
    await _auth(client, user.id)

    resp = await client.get("/settings/billing")

    assert resp.status_code == 200
    assert '<a href="/settings/billing" class="settings-popup-item">' in resp.text

    scope_row = (
        await session.execute(
            select(UserSetting).where(
                UserSetting.user_id == user.id,
                UserSetting.field_key == "billing_scope",
            )
        )
    ).scalar_one_or_none()
    plan_row = (
        await session.execute(
            select(UserSetting).where(
                UserSetting.user_id == user.id,
                UserSetting.field_key == "billing_plan",
            )
        )
    ).scalar_one_or_none()
    assert scope_row is not None and scope_row.value == "user"
    assert plan_row is not None and plan_row.value == "free_trial"


async def test_billing_setup_session_redirects_when_stripe_not_configured(
    client: AsyncClient,
    session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "stripe_secret_key", "", raising=False)

    org, user = await seed_org(session)
    await session.commit()
    await _auth(client, user.id)

    resp = await client.post(
        "/settings/billing/stripe/setup-session",
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/settings/billing?stripe=config-missing"


async def test_billing_setup_session_recovers_stale_customer_id(
    client: AsyncClient,
    session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "stripe_secret_key", "sk_test_dummy", raising=False)

    org, user = await seed_org(session)
    session.add(
        UserSetting(
            id=uuid.uuid4(),
            user_id=user.id,
            org_id=org.id,
            field_key="stripe_customer_id",
            value="cus_stale",
        )
    )
    await session.commit()
    await _auth(client, user.id)

    calls: list[tuple[str, str, str | None]] = []

    async def _fake_stripe_api_request(method, endpoint, *, data=None, params=None):
        customer = None
        if isinstance(data, list):
            for k, v in data:
                if k == "customer":
                    customer = v
                    break
        calls.append((method, endpoint, customer))

        if endpoint == "/v1/checkout/sessions" and customer == "cus_stale":
            raise HTTPException(status_code=502, detail="Stripe API error: No such customer: 'cus_stale'")
        if endpoint == "/v1/customers":
            return {"id": "cus_fresh"}
        if endpoint == "/v1/checkout/sessions":
            return {"url": "https://checkout.stripe.com/c/pay/test_checkout_url"}
        return {}

    monkeypatch.setattr(ui, "_stripe_api_request", _fake_stripe_api_request)

    resp = await client.post(
        "/settings/billing/stripe/setup-session",
        follow_redirects=False,
    )

    assert resp.status_code == 303
    assert resp.headers["location"] == "https://checkout.stripe.com/c/pay/test_checkout_url"
    assert (
        ("POST", "/v1/checkout/sessions", "cus_stale") in calls
        and ("POST", "/v1/customers", None) in calls
        and ("POST", "/v1/checkout/sessions", "cus_fresh") in calls
    )


async def test_embedded_mock_session_uses_embedded_page_ui_mode(
    client: AsyncClient,
    session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "stripe_secret_key", "sk_test_dummy", raising=False)
    monkeypatch.setattr(settings, "stripe_publishable_key", "pk_test_dummy", raising=False)

    org, user = await seed_org(session)
    await session.commit()
    await _auth(client, user.id)

    captured: dict[str, str] = {}

    async def _fake_stripe_api_request(method, endpoint, *, data=None, params=None):
        if endpoint == "/v1/customers":
            return {"id": "cus_embedded"}
        if endpoint == "/v1/checkout/sessions":
            if isinstance(data, list):
                for k, v in data:
                    if k == "ui_mode":
                        captured["ui_mode"] = v
            return {"client_secret": "cs_test_embedded_secret"}
        return {}

    monkeypatch.setattr(ui, "_stripe_api_request", _fake_stripe_api_request)

    resp = await client.post("/mock/billing/embedded/session")

    assert resp.status_code == 200
    assert resp.json() == {"clientSecret": "cs_test_embedded_secret"}
    assert captured.get("ui_mode") == "embedded_page"


async def test_settings_billing_embedded_session_setup_intent_uses_embedded_page(
    client: AsyncClient,
    session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "stripe_secret_key", "sk_test_dummy", raising=False)
    monkeypatch.setattr(settings, "stripe_publishable_key", "pk_test_dummy", raising=False)

    org, user = await seed_org(session)
    await session.commit()
    await _auth(client, user.id)

    captured: dict[str, str] = {}

    async def _fake_stripe_api_request(method, endpoint, *, data=None, params=None):
        if endpoint == "/v1/customers":
            return {"id": "cus_settings"}
        if endpoint == "/v1/checkout/sessions":
            if isinstance(data, list):
                for k, v in data:
                    if k in {"mode", "ui_mode"}:
                        captured[k] = v
            return {"client_secret": "cs_test_setup_secret"}
        return {}

    monkeypatch.setattr(ui, "_stripe_api_request", _fake_stripe_api_request)

    resp = await client.post(
        "/settings/billing/stripe/embedded-session",
        json={"intent": "setup"},
    )

    assert resp.status_code == 200
    assert resp.json()["clientSecret"] == "cs_test_setup_secret"
    assert captured.get("mode") == "setup"
    assert captured.get("ui_mode") == "embedded_page"


async def test_settings_billing_embedded_session_subscribe_pro_monthly_uses_price(
    client: AsyncClient,
    session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "stripe_secret_key", "sk_test_dummy", raising=False)
    monkeypatch.setattr(settings, "stripe_publishable_key", "pk_test_dummy", raising=False)
    monkeypatch.setattr(settings, "stripe_price_pro_monthly", "price_pro_test_123", raising=False)

    org, user = await seed_org(session)
    await session.commit()
    await _auth(client, user.id)

    captured: dict[str, str] = {}

    async def _fake_stripe_api_request(method, endpoint, *, data=None, params=None):
        if endpoint == "/v1/customers":
            return {"id": "cus_settings"}
        if endpoint == "/v1/checkout/sessions":
            if isinstance(data, list):
                for k, v in data:
                    if k in {"mode", "ui_mode", "line_items[0][price]", "line_items[0][quantity]", "subscription_data[trial_period_days]"}:
                        captured[k] = v
            return {"client_secret": "cs_test_subscribe_pro_secret"}
        return {}

    monkeypatch.setattr(ui, "_stripe_api_request", _fake_stripe_api_request)

    resp = await client.post(
        "/settings/billing/stripe/embedded-session",
        json={"intent": "subscribe_pro_monthly"},
    )

    assert resp.status_code == 200
    assert resp.json()["clientSecret"] == "cs_test_subscribe_pro_secret"
    assert captured.get("mode") == "subscription"
    assert captured.get("ui_mode") == "embedded_page"
    assert captured.get("line_items[0][price]") == "price_pro_test_123"
    assert captured.get("line_items[0][quantity]") == "1"
    assert captured.get("subscription_data[trial_period_days]") == "30"


async def test_settings_billing_embedded_session_subscribe_pro_annual_uses_price(
    client: AsyncClient,
    session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "stripe_secret_key", "sk_test_dummy", raising=False)
    monkeypatch.setattr(settings, "stripe_publishable_key", "pk_test_dummy", raising=False)
    monkeypatch.setattr(settings, "stripe_price_pro_annual", "price_pro_annual_test_123", raising=False)

    org, user = await seed_org(session)
    await session.commit()
    await _auth(client, user.id)

    captured: dict[str, str] = {}

    async def _fake_stripe_api_request(method, endpoint, *, data=None, params=None):
        if endpoint == "/v1/customers":
            return {"id": "cus_settings"}
        if endpoint == "/v1/checkout/sessions":
            if isinstance(data, list):
                for k, v in data:
                    if k in {"mode", "ui_mode", "line_items[0][price]", "line_items[0][quantity]", "subscription_data[trial_period_days]"}:
                        captured[k] = v
            return {"client_secret": "cs_test_subscribe_pro_annual_secret"}
        return {}

    monkeypatch.setattr(ui, "_stripe_api_request", _fake_stripe_api_request)

    resp = await client.post(
        "/settings/billing/stripe/embedded-session",
        json={"intent": "subscribe_pro_annual"},
    )

    assert resp.status_code == 200
    assert resp.json()["clientSecret"] == "cs_test_subscribe_pro_annual_secret"
    assert captured.get("mode") == "subscription"
    assert captured.get("ui_mode") == "embedded_page"
    assert captured.get("line_items[0][price]") == "price_pro_annual_test_123"
    assert captured.get("line_items[0][quantity]") == "1"
    assert captured.get("subscription_data[trial_period_days]") == "30"


async def test_settings_billing_set_default_payment_method_updates_customer(
    client: AsyncClient,
    session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "stripe_secret_key", "sk_test_dummy", raising=False)

    org, user = await seed_org(session)
    session.add(
        UserSetting(
            id=uuid.uuid4(),
            user_id=user.id,
            org_id=org.id,
            field_key="stripe_customer_id",
            value="cus_for_default",
        )
    )
    await session.commit()
    await _auth(client, user.id)

    captured: dict[str, str] = {}

    async def _fake_stripe_api_request(method, endpoint, *, data=None, params=None):
        captured["method"] = method
        captured["endpoint"] = endpoint
        if isinstance(data, list):
            for k, v in data:
                if k == "invoice_settings[default_payment_method]":
                    captured["default_pm"] = v
        return {}

    monkeypatch.setattr(ui, "_stripe_api_request", _fake_stripe_api_request)

    resp = await client.post(
        "/settings/billing/stripe/payment-method/default",
        data={"payment_method_id": "pm_new_default"},
        follow_redirects=False,
    )

    assert resp.status_code == 303
    assert resp.headers["location"] == "/settings/billing?stripe=card-default-updated"
    assert captured.get("method") == "POST"
    assert captured.get("endpoint") == "/v1/customers/cus_for_default"
    assert captured.get("default_pm") == "pm_new_default"


async def test_settings_billing_remove_payment_method_sets_fallback_default(
    client: AsyncClient,
    session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "stripe_secret_key", "sk_test_dummy", raising=False)

    org, user = await seed_org(session)
    session.add(
        UserSetting(
            id=uuid.uuid4(),
            user_id=user.id,
            org_id=org.id,
            field_key="stripe_customer_id",
            value="cus_for_remove",
        )
    )
    await session.commit()
    await _auth(client, user.id)

    calls: list[tuple[str, str, str | None]] = []

    async def _fake_stripe_api_request(method, endpoint, *, data=None, params=None):
        value: str | None = None
        if isinstance(data, list):
            for k, v in data:
                if k == "invoice_settings[default_payment_method]":
                    value = v
                    break
        calls.append((method, endpoint, value))
        return {}

    async def _fake_get_default(customer_id: str):
        return "pm_old_default"

    async def _fake_list_cards(customer_id: str):
        return [
            {"id": "pm_fallback", "brand": "Visa", "last4": "4242", "exp": "01/2030", "is_default": False},
        ]

    monkeypatch.setattr(ui, "_stripe_api_request", _fake_stripe_api_request)
    monkeypatch.setattr(ui, "_get_customer_default_payment_method", _fake_get_default)
    monkeypatch.setattr(ui, "_list_stripe_payment_methods", _fake_list_cards)

    resp = await client.post(
        "/settings/billing/stripe/payment-method/remove",
        data={"payment_method_id": "pm_old_default"},
        follow_redirects=False,
    )

    assert resp.status_code == 303
    assert resp.headers["location"] == "/settings/billing?stripe=card-removed"
    assert ("POST", "/v1/payment_methods/pm_old_default/detach", None) in calls
    assert ("POST", "/v1/customers/cus_for_remove", "pm_fallback") in calls
