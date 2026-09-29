"""Bug: every button on the pro forma review page was dead.

addUnitRow() in app/templates/partials/proforma_review.html closed its
template literal with an escaped backtick (``</td>\\`;``), so the literal ran
on into addOpexRow() and the whole <script> block was a SyntaxError
(introduced 84016b2c, 2026-05-29). The browser then defined none of the
page's functions: "+ Add unit type", "+ Add OpEx line", the row-uncheck
dimming, the Current/Market rent toggle, the Unit/Flat toggle and the
selected-expense total all did nothing. Fixed by dropping the backslash.

The check is on the rendered page (the review fragment served by
GET /ui/models/{id}/proforma-status/{task_id} when a parse is done): the
script must contain no escaped backtick, and its backticks must pair up.
When Node is on PATH the extracted script is also syntax-checked with it.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import seed_deal_model, seed_opportunity, seed_org, set_client_auth

pytestmark = pytest.mark.asyncio


class _FakeRedis:
    def __init__(self, store: dict, decode: bool):
        self._s, self._d = store, decode

    def get(self, key):
        v = self._s.get(key)
        if v is None:
            return None
        return v.decode() if self._d else v

    def set(self, key, value, ex=None):
        self._s[key] = value.encode() if isinstance(value, str) else value
        return True


async def test_review_page_script_parses(
    client: AsyncClient, session: AsyncSession, monkeypatch, tmp_path
) -> None:
    import redis  # type: ignore

    store: dict = {}
    monkeypatch.setattr(
        redis, "from_url",
        lambda _u, decode_responses=False, **_k: _FakeRedis(store, decode_responses),
    )
    org, user = await seed_org(session)
    opp = await seed_opportunity(session, org, user)
    scen = await seed_deal_model(session, opp, user)
    await session.commit()
    set_client_auth(client, user.id)

    store["proforma:t:progress"] = json.dumps({"status": "done"}).encode()
    store["proforma:t:result"] = json.dumps(
        {"unit_types": [], "expense_lines": [], "warnings": []}
    ).encode()
    page = await client.get(
        f"/ui/models/{scen.id}/proforma-status/t", headers={"hx-request": "true"}
    )
    assert page.status_code == 200

    scripts = re.findall(r"<script>(.*?)</script>", page.text, re.S)
    script = next(s for s in scripts if "function addUnitRow" in s)
    assert "\\`" not in script, "escaped backtick leaves a template literal unterminated"
    assert script.count("`") % 2 == 0

    node = shutil.which("node")
    if node:
        js = tmp_path / "review.js"
        js.write_text(script, encoding="utf-8")
        res = subprocess.run([node, "--check", str(js)], capture_output=True, text=True)
        assert res.returncode == 0, res.stderr
