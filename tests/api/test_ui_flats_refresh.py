"""The county-copy page: every dated copy, the gate, promote and roll back.

The page is the one place a person sees what stands between a refreshed copy
of the county map and the site showing it. What is driven here is that it
tells the truth about the rows and does only what the service allows: the
gate is shown whole (nine rows, tripped or not), a standing gate refuses a
plain promote and re-renders with the reason, an override promotes and is
recorded under the person's name, a clean gate promotes with no reason asked,
and a rollback puts the previous copy back. The rows come from the service
test's world: a July copy in use and a September candidate with three lot
changes and four decisions between them.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.flats import FlatsRun, FlatsSnapshot
from app.services.flats_refresh import drift
from tests.conftest import seed_org, set_client_auth
from tests.services.test_flats_refresh import _world

pytestmark = pytest.mark.asyncio


async def _login(client: AsyncClient, session: AsyncSession):
    _org, user = await seed_org(session)
    await session.commit()
    set_client_auth(client, user.id)
    return user


def _card(body: str, snapshot_id: int) -> str:
    return body.split(f'id="snapshot-{snapshot_id}"', 1)[1].split('<div class="card"', 1)[0]


async def _statuses(session: AsyncSession, w: dict) -> tuple[str, str, str, str]:
    session.expunge_all()
    july = await session.get(FlatsSnapshot, w["july"].id)
    sept = await session.get(FlatsSnapshot, w["sept"].id)
    old = await session.get(FlatsRun, 2)
    new = await session.get(FlatsRun, 4)
    return july.status, sept.status, old.status, new.status


async def test_the_page_shows_both_copies_and_the_whole_gate(client: AsyncClient, session: AsyncSession, tmp_path) -> None:
    await _login(client, session)
    w = await _world(session, tmp_path)

    page = await client.get("/flats/refresh")

    assert page.status_code == 200
    body = page.text
    assert "County copy" in body and "The county map copy" in body
    # Newest first: the candidate's card comes before the copy in use.
    assert body.index(f'id="snapshot-{w["sept"].id}"') < body.index(f'id="snapshot-{w["july"].id}"')

    sept = _card(body, w["sept"].id)
    assert "Copy taken 2026-09-18" in sept and ">candidate<" in sept
    assert "run 4 (candidate, rules r1, code bbbb)" in sept
    assert f'href="/flats/lots?run=4"' in sept
    # The gate is shown whole: nine rows, and only the missing drift report stands.
    gate = sept.split(f'id="gate-{w["sept"].id}"', 1)[1].split("</table>", 1)[0]
    assert gate.count("<tr ") == 9
    assert gate.count('data-tripped="yes"') == 1
    assert 'data-code="no_drift" data-tripped="yes"' in gate
    assert "the verdict drift was run and stored" in gate
    assert "every layer downloaded whole" in gate
    # The delta summary and the override form, since the gate stands.
    assert f'id="delta-{w["sept"].id}"' in sept and "3 changed" in sept and "1 of those put an earlier decision in doubt" in sept
    assert "Not clean: no_drift" in sept
    assert 'name="override"' in sept and "Promote over the warning" in sept
    assert f'id="drift-{w["sept"].id}"' not in sept

    july = _card(body, w["july"].id)
    assert "Copy taken 2026-07-28" in july and ">current<" in july
    assert "run 2 (complete, rules r1, code aaaa)" in july
    # Nothing promoted the July copy (it is the synthetic first copy), so there is nothing to roll back to.
    assert f'id="rollback-{w["july"].id}"' not in july
    assert f'id="gate-{w["july"].id}"' not in july


async def test_a_standing_gate_refuses_a_plain_promote_and_says_why(client: AsyncClient, session: AsyncSession, tmp_path) -> None:
    await _login(client, session)
    w = await _world(session, tmp_path)

    answer = await client.post("/flats/refresh/promote", data={"snapshot": str(w["sept"].id), "override": ""})

    assert answer.status_code == 422
    assert 'id="refresh-error"' in answer.text
    assert "the gate is not clean: no_drift" in answer.text
    assert await _statuses(session, w) == ("current", "candidate", "complete", "candidate")


async def test_an_override_promotes_under_the_persons_name_and_flags_the_decisions(
    client: AsyncClient, session: AsyncSession, tmp_path
) -> None:
    user = await _login(client, session)
    w = await _world(session, tmp_path)

    answer = await client.post(
        "/flats/refresh/promote",
        data={"snapshot": str(w["sept"].id), "override": "read the delta myself; the drift can wait"},
    )

    assert answer.status_code == 303
    assert answer.headers["location"].startswith("/flats/refresh?done=")
    assert await _statuses(session, w) == ("retired", "current", "complete", "complete")
    sept = await session.get(FlatsSnapshot, w["sept"].id)
    assert sept.promoted_by == user.name
    assert "over no_drift by Test User: read the delta myself" in sept.notes

    page = await client.get(answer.headers["location"])
    body = page.text
    assert 'id="refresh-done"' in body
    assert "Copy 2026-09-18 is the copy in use; run 4 is the Lots pages" in body
    assert "3 review decisions marked look again" in body
    card = _card(body, w["sept"].id)
    assert ">current<" in card and f"by {user.name}" in card
    assert f'id="flagged-{w["sept"].id}"' in card and "3 review decisions were made about ground this copy shows" in card
    # A promoted copy can be rolled back from its card; the retired one cannot.
    assert f'id="rollback-{w["sept"].id}"' in card
    assert f'id="rollback-{w["july"].id}"' not in body
    # And the Lots pages' default is the new run.
    lots = await client.get("/flats/lots")
    assert lots.status_code == 200


async def test_a_clean_gate_promotes_with_no_reason_asked(client: AsyncClient, session: AsyncSession, tmp_path) -> None:
    await _login(client, session)
    w = await _world(session, tmp_path)
    await drift(session, from_run=2, to_run=4)
    await session.commit()

    page = await client.get("/flats/refresh")
    card = _card(page.text, w["sept"].id)
    gate = card.split(f'id="gate-{w["sept"].id}"', 1)[1].split("</table>", 1)[0]
    # Every gate row quiet: the drift ran and every move had a cause.
    assert gate.count('data-tripped="yes"') == 0
    assert f'id="drift-{w["sept"].id}"' in card
    assert "6 answers compared with run 2" in card and "unexplained 0" in card
    # The causes are named in the order they are tried.
    assert "by the ground 2" in card and "by the map around the lot 0" in card and "sat on a line 0" in card
    assert "by a code change 1" in card
    assert f'id="drift-surroundings-{w["sept"].id}"' not in card
    assert "Promote — make this the copy in use" in card
    assert 'name="override"' not in card

    answer = await client.post("/flats/refresh/promote", data={"snapshot": str(w["sept"].id)})

    assert answer.status_code == 303
    assert await _statuses(session, w) == ("retired", "current", "complete", "complete")
    sept = await session.get(FlatsSnapshot, w["sept"].id)
    assert "over" not in sept.notes


async def test_rollback_needs_a_reason_and_puts_the_previous_copy_back(client: AsyncClient, session: AsyncSession, tmp_path) -> None:
    await _login(client, session)
    w = await _world(session, tmp_path)
    await client.post("/flats/refresh/promote", data={"snapshot": str(w["sept"].id), "override": "testing the undo"})
    assert await _statuses(session, w) == ("retired", "current", "complete", "complete")

    refused = await client.post("/flats/refresh/rollback", data={"reason": "  "})
    assert refused.status_code == 422
    assert 'id="refresh-error"' in refused.text
    assert await _statuses(session, w) == ("retired", "current", "complete", "complete")

    answer = await client.post("/flats/refresh/rollback", data={"reason": "the September answers look wrong"})

    assert answer.status_code == 303
    assert await _statuses(session, w) == ("current", "candidate", "complete", "candidate")
    page = await client.get(answer.headers["location"])
    assert "Copy 2026-07-28 is the copy in use again; copy 2026-09-18 is a candidate." in page.text
    sept = _card(page.text, w["sept"].id)
    assert ">candidate<" in sept and "rolled back" in sept


async def test_the_page_stands_with_no_copy_registered(client: AsyncClient, session: AsyncSession) -> None:
    await _login(client, session)

    page = await client.get("/flats/refresh")

    assert page.status_code == 200
    assert "No county map copy has been registered." in page.text


async def test_new_zone_codes_are_the_warning_and_ruled_ones_fold_away(client: AsyncClient, session: AsyncSession, tmp_path) -> None:
    """Steph 2026-09-20: a code is ruled once, with the reason written down,
    and never shown as a question again; the page asks only about a code
    nobody has ruled on. The ruled ones -- forbidden uses answered red at the
    use gate, aliases, pockets, the unencodable, the still-to-read -- are
    there to read, folded under a summary line."""
    await _login(client, session)
    w = await _world(session, tmp_path)
    sept = await session.get(FlatsSnapshot, w["sept"].id)
    sept.counts = {
        **(sept.counts or {}),
        "new_zones": {"or/clackamas/happy-valley": {"MURX9": 3}},
        "ruled_zones": {
            "or/clackamas/happy-valley": {"pocket": {"FU10": 12, "RRFF5": 95}, "to_read": {"NSA": 64}},
            "or/clackamas/_unincorporated": {"unencodable": {"HDR": 251}},
        },
        "prohibited_by_zone": {"or/clackamas/_unincorporated/C3": 447, "or/clackamas/gladstone/LI": 27},
    }
    await session.flush()

    card = _card((await client.get("/flats/refresh")).text, w["sept"].id)
    assert "Zone codes nobody has ruled on" in card
    assert "<strong>or/clackamas/happy-valley</strong>: MURX9 (3)" in card
    assert "a district the city created or renamed" in card
    assert "Zone codes already ruled on" in card
    assert "2 forbid the building (474 lots red at the use gate)" in card
    assert "or/clackamas/_unincorporated/C3 (447)" in card
    assert "<strong>or/clackamas/happy-valley</strong> another jurisdiction&#39;s zoning inside the line: FU10 (12), RRFF5 (95)" in card
    assert "<strong>or/clackamas/happy-valley</strong> seen; use table still to read: NSA (64)" in card
    assert "<strong>or/clackamas/_unincorporated</strong> read; asks a measurement the screen cannot take: HDR (251)" in card

    # With nothing new and nothing ruled, neither block renders.
    sept.counts = {k: v for k, v in sept.counts.items() if k not in ("new_zones", "ruled_zones", "prohibited_by_zone")}
    await session.flush()
    card = _card((await client.get("/flats/refresh")).text, w["sept"].id)
    assert "Zone codes nobody has ruled on" not in card and "Zone codes already ruled on" not in card
