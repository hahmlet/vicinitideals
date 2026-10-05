"""The Unknowns page: approving a kind of flag's numbers and the colour rule.

What these hold to: the page is reachable past the ``/flats/{layer}``
catch-all, only the owner can approve, an approval is a stored row and not a
file edit (the drain does that), and a value the files would refuse is
refused here, before it can sit in the queue as if it could be written.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.flats import (
    RULES_SUBJECT,
    FlatsFlagDecision,
    FlatsFlagInstance,
    FlatsFlagQuestion,
    FlatsFlagReport,
)
from app.services import flats_flags
from flats.score import flags as fp
from tests.conftest import seed_org, set_client_auth

pytestmark = pytest.mark.asyncio


async def _login(client: AsyncClient, session: AsyncSession, *, owner: bool):
    _org, user = await seed_org(session)
    user.is_admin = owner
    await session.commit()
    set_client_auth(client, user.id)
    return user


def _a_code() -> str:
    return next(iter(fp.load_registry())).code


def _type_form(code: str, **over) -> dict:
    t = fp.load_registry()[code]
    return {
        "code": code,
        "risk": t.risk.value,
        "severity": str(t.severity),
        "absorbs": t.absorbs or "",
        "resolution": t.resolution.value,
        "priority": "now",
        "note": "",
        **over,
    }


def _rules_form(**over) -> dict:
    r = fp.load_rules()
    bands = {getattr(k, "value", k): v for k, v in r.risk_bands.items()}
    return {
        "yellow_at_severity": str(r.yellow_at_severity),
        "approval_severity": str(r.approval_severity),
        "near_miss_fit_ft": str(r.near_miss["fit_ft"]),
        "near_miss_severity": str(r.near_miss_severity),
        **{f"risk_{k}": str(round(v * 100)) for k, v in bands.items()},
        "note": "",
        **over,
    }


async def _stored(session: AsyncSession) -> list[FlatsFlagDecision]:
    return list((await session.execute(select(FlatsFlagDecision))).scalars())


async def test_the_page_is_not_swallowed_by_the_layer_route(client, session):
    await _login(client, session, owner=False)

    response = await client.get("/flats/flags")

    assert response.status_code == 200
    assert "Unknowns" in response.text
    assert "The colour rule" in response.text
    # Every kind is listed, and a non-owner gets no approve button.
    assert response.text.count("data-flag=") == len(fp.load_registry())
    assert "data-approve" not in response.text
    assert "read-only for you" in response.text


async def test_the_owner_sees_the_forms_and_waiting_kinds_first(client, session):
    await _login(client, session, owner=True)

    response = await client.get("/flats/flags")

    assert response.status_code == 200
    assert "data-approve" in response.text
    pending = sum(t.status is fp.TypeStatus.pending for t in fp.load_registry())
    if pending:
        first = response.text.index('data-section="')
        assert response.text[first:].startswith('data-section="proposed"')


async def test_an_approval_is_a_stored_row_waiting_for_the_write_in(client, session):
    user = await _login(client, session, owner=True)
    code = _a_code()
    before = fp.load_registry()[code]

    response = await client.post(
        "/ui/flats/flags/type", data=_type_form(code, severity="7", note="checked")
    )

    assert response.status_code == 200
    assert 'data-state="waiting"' in response.text
    assert "in force at the next write-in" in response.text
    rows = await _stored(session)
    assert len(rows) == 1
    row = rows[0]
    assert row.subject == code
    assert row.values["severity"] == 7
    assert row.values["priority"] == "now"
    assert row.note == "checked"
    assert row.decided_by == user.name
    assert row.decided_user_id == user.id
    assert row.exported_at is None
    # Not a file edit: the files change only when the drain writes them.
    assert fp.load_registry()[code] == before

    page = await client.get("/flats/flags")
    assert f'id="flag-{code}"' in page.text
    block = page.text[page.text.index(f'id="flag-{code}"') - 200 :][:400]
    assert 'data-state="waiting"' in block


async def test_a_non_owner_cannot_approve(client, session):
    await _login(client, session, owner=False)

    response = await client.post("/ui/flats/flags/type", data=_type_form(_a_code()))

    assert response.status_code == 403
    assert await _stored(session) == []


async def test_signed_out_cannot_approve(client, session):
    response = await client.post("/ui/flats/flags/type", data=_type_form(_a_code()))

    assert response.status_code in (401, 303, 307)
    assert await _stored(session) == []


async def test_an_unknown_kind_is_not_found(client, session):
    await _login(client, session, owner=True)

    response = await client.post(
        "/ui/flats/flags/type", data={**_type_form(_a_code()), "code": "NO-SUCH-KIND"}
    )

    assert response.status_code == 404
    assert await _stored(session) == []


@pytest.mark.parametrize("over", [{"severity": "11"}, {"risk": "sometimes"}, {"absorbs": "roof"}])
async def test_a_value_the_files_would_refuse_is_refused_here(client, session, over):
    await _login(client, session, owner=True)

    response = await client.post("/ui/flats/flags/type", data=_type_form(_a_code(), **over))

    assert response.status_code == 200
    assert "data-error" in response.text
    assert await _stored(session) == []


async def test_the_colour_rule_is_approved_in_percent_and_stored_as_a_probability(
    client, session
):
    await _login(client, session, owner=True)

    response = await client.post(
        "/ui/flats/flags/rules", data=_rules_form(yellow_at_severity="4", risk_possible="35")
    )

    assert response.status_code == 200
    assert 'data-state="waiting"' in response.text
    rows = await _stored(session)
    assert len(rows) == 1
    assert rows[0].subject == RULES_SUBJECT
    assert rows[0].values["yellow_at_severity"] == 4
    assert rows[0].values["risk_bands"]["possible"] == 0.35
    # Shown back in percent.
    assert 'name="risk_possible"' in response.text
    assert 'value="35"' in response.text


async def test_a_colour_rule_the_file_would_refuse_is_refused_here(client, session):
    await _login(client, session, owner=True)

    response = await client.post(
        "/ui/flats/flags/rules", data=_rules_form(yellow_at_severity="11")
    )

    assert response.status_code == 200
    assert "data-error" in response.text
    assert (await session.execute(select(func.count()).select_from(FlatsFlagDecision))).scalar() == 0


CORNER = ("FACT-CORNER-LOT", "or/multnomah/portland|corner_lot")


async def _open_on(session: AsyncSession, colours: list[str]) -> None:
    """Corner-lot instances open on one lot per colour (no run behind them:
    the page counts the history, not a run)."""
    for i, colour in enumerate(colours):
        session.add(FlatsFlagInstance(county="multnomah", tlid=f"LOT{i}", design_key="pod56x36@2",
                                      code=CORNER[0], key=CORNER[1], raised_by="FACT_UNOBSERVED", colour=colour))
    await session.commit()


async def test_each_kind_says_how_many_lots_it_holds_open_now(client, session):
    await _login(client, session, owner=False)
    await _open_on(session, ["yellow", "yellow", "red"])

    page = await client.get("/flats/flags")

    row = page.text.split(f'data-flag="{CORNER[0]}"', 1)[1].split('class="flag-row', 1)[0]
    assert 'data-open-lots="3"' in row
    assert "Open on 3 lots now" in row and "2 yellow" in row and "1 red" in row
    assert page.text.count("data-open-lots=") == 1
    assert 'id="questions-link"' in page.text


async def test_a_question_waits_on_the_queue_and_the_owner_answers_it(client, session):
    await _login(client, session, owner=True)
    await _open_on(session, ["yellow", "red"])
    q = await flats_flags.ask(session, code=CORNER[0], key=CORNER[1], by="agent 2026-10-04",
                              question="Does Portland count a lot on a curve as a corner?")
    await session.commit()

    page = await client.get("/flats/flags/questions")
    assert page.status_code == 200
    waiting = page.text.split('data-section="waiting"', 1)[1].split('data-section="answered"', 1)[0]
    assert "Does Portland count a lot on a curve as a corner?" in waiting
    assert "open on 2 lots" in waiting and "1 yellow" in waiting and "1 red" in waiting
    assert f'action="/ui/flats/flags/questions/{q.id}/answer"' in waiting

    done = await client.post(f"/ui/flats/flags/questions/{q.id}/answer",
                             data={"answer": "Only where the curve turns 45 degrees or more."})
    assert done.status_code == 303
    after = await client.get("/flats/flags/questions")
    assert 'id="q-none-waiting"' in after.text
    answered = after.text.split('data-section="answered"', 1)[1]
    assert "Only where the curve turns 45 degrees or more." in answered
    assert "still open on 2 lots until it is encoded" in answered

    again = await client.post(f"/ui/flats/flags/questions/{q.id}/answer", data={"answer": "Twice."})
    assert again.status_code == 303 and "error=" in again.headers["location"]


async def test_only_the_owner_answers_a_question(client, session):
    await _login(client, session, owner=False)
    q = await flats_flags.ask(session, code=CORNER[0], key=CORNER[1], by="agent",
                              question="Does Portland count a lot on a curve as a corner?")
    await session.commit()

    page = await client.get("/flats/flags/questions")
    assert "Does Portland count" in page.text and "/answer" not in page.text
    refused = await client.post(f"/ui/flats/flags/questions/{q.id}/answer", data={"answer": "Yes, always."})
    assert refused.status_code == 403
    (row,) = (await session.execute(select(FlatsFlagQuestion))).scalars()
    await session.refresh(row)
    assert row.answer is None


async def test_the_work_queue_lists_each_open_question_with_its_lots(client, session):
    await _login(client, session, owner=False)
    await _open_on(session, ["yellow", "yellow", "red"])

    page = await client.get("/flats/flags/queue")

    assert page.status_code == 200
    row = page.text.split(f'data-flag="{CORNER[0]}"', 1)[1].split("</tr>", 1)[0]
    assert "or/multnomah/portland · corner_lot" in row
    assert "0 · 2 · 1" in row
    # Each yellow lot is held by the corner question alone.
    assert 'data-last="2"' in row
    assert 'id="queue-empty"' not in page.text


async def test_the_work_queue_says_when_nothing_is_open(client, session):
    await _login(client, session, owner=False)

    page = await client.get("/flats/flags/queue")

    assert page.status_code == 200 and 'id="queue-empty"' in page.text


async def test_the_report_page_shows_the_newest_nightly_check(client, session):
    await _login(client, session, owner=False)
    page = await client.get("/flats/flags/report")
    assert page.status_code == 200 and 'id="report-none"' in page.text

    session.add(FlatsFlagReport(ok=False, report={
        "rows": 1200, "kinds": 68, "pending_kinds": ["FACT-CORNER-LOT"], "steps": [-1, 1],
        "moved": {"green->yellow": 3},
        "moved_examples": [{"county": "multnomah", "tlid": "1S2E08BA  -09500", "design": "pod56x36@2"}],
        "incomplete": {}, "incomplete_examples": [], "unregistered_instances": {},
        "sensitivity": {"pod56x36@2": {"1": {"moves": {"yellow->red": 40, "green->red": 2},
                                              "examples": [{"county": "multnomah", "tlid": "1N1E29DD  -05600",
                                                            "design": "pod56x36@2", "move": "green->red"}],
                                              "keys": {"FACT-CORNER-LOT|or/multnomah/portland|corner_lot": 12}}}},
    }))
    await session.commit()

    page = await client.get("/flats/flags/report")

    check = page.text.split('id="check-result"', 1)[1]
    assert 'data-ok="no"' in page.text and "needs a look" in check
    assert "3 green → yellow" in check and "1S2E08BA" in check
    assert "1 of 68 kinds" in check
    pod = page.text.split('id="sensitivity-pod56x36-2"', 1)[1]
    narrower, wider = pod.split('class="sensitivity-step"')[1:3]
    assert "1 ft narrower" in narrower and 'data-total="0"' in narrower
    assert "1 ft wider" in wider and 'data-total="42"' in wider
    assert "40 yellow → red" in wider and "FACT-CORNER-LOT · or/multnomah/portland · corner_lot (12)" in wider
    assert "1N1E29DD" in wider


async def test_the_report_page_shows_the_room_and_the_limits_a_bigger_pod_crosses(client, session):
    # FOLLOWUPS 37(ii): a report written after the bridge kept the room on
    # each pass names the limits that moved each lot, tries the pod taller
    # and lower, and says how close the green lots came to each limit.
    await _login(client, session, owner=False)
    session.add(FlatsFlagReport(ok=True, report={
        "rows": 1200, "kinds": 68, "pending_kinds": [], "steps": [1], "height_steps": [-1, 2],
        "moved": {}, "moved_examples": [], "incomplete": {}, "incomplete_examples": [], "unregistered_instances": {},
        "sensitivity": {"pod56x36@2": {"1": {"moves": {"green->red": 5}, "examples": [], "keys": {},
                                              "limits": {"coverage_pct": 4, "fit_ft": 1}}}},
        "height": {"pod56x36@2": {"2": {"moves": {"green->red": 7}, "examples": [], "keys": {},
                                         "limits": {"height_ft": 7}}}},
        "room": {
            "pod56x36@2": {"green": 300, "measured": 300, "checks": {
                "far": {"lots": 300, "median": 0.25, "within_10": 3, "within_5": 1},
                "height_ft": {"lots": 280, "median": 4.0, "within_10": 70, "within_5": 30},
            }},
            "pod40x30@1": {"green": 12, "measured": 0, "checks": {}},
        },
    }))
    await session.commit()

    page = await client.get("/flats/flags/report")

    assert page.status_code == 200 and 'id="room-heading"' in page.text
    room = page.text.split('id="room-pod56x36-2"', 1)[1].split('class="card"', 1)[0]
    # The limit most lots come close to is first.
    first, second = room.split('class="room-row"')[1:3]
    assert 'data-check="height_ft"' in first and 'data-within-10="70"' in first
    assert "Height" in first and "4.0 ft" in first
    assert 'data-check="far"' in second and "Floor area ratio" in second and "0.25" in second
    # A run screened before the room was kept says so, not "nothing close".
    old = page.text.split('id="room-pod40x30-1"', 1)[1].split('class="card"', 1)[0]
    assert "screened before the room was kept" in old
    wider = page.text.split('id="sensitivity-pod56x36-2"', 1)[1].split('class="sensitivity-step"')[1]
    assert "Building coverage (4)" in wider and "The fit, inside the setbacks" in wider
    tall = page.text.split('id="height-pod56x36-2"', 1)[1]
    lower, taller = tall.split('class="height-step"')[1:3]
    assert "1 ft lower" in lower and 'data-total="0"' in lower
    assert "2 ft taller" in taller and 'data-total="7"' in taller and "Height (7)" in taller


async def test_the_report_page_shows_how_much_bigger_the_pod_could_be_each_way(client, session):
    # FOLLOWUPS 37(ii), every direction: the room wider, deeper and both
    # ways at once on each green lot's own shape, and what each move does.
    await _login(client, session, owner=False)
    step = {"examples": [], "keys": {}}
    session.add(FlatsFlagReport(ok=True, report={
        "rows": 1200, "kinds": 68, "pending_kinds": [], "steps": [-1, 2], "height_steps": [],
        "moved": {}, "moved_examples": [], "incomplete": {}, "incomplete_examples": [], "unregistered_instances": {},
        "sensitivity": {"pod56x36@2": {"2": {**step, "moves": {"green->red": 3}, "limits": {"fit_ft": 3}}}},
        "depth": {"pod56x36@2": {"2": {**step, "moves": {"green->yellow": 9}, "limits": {"fit_ft": 9}}}},
        "both": {"pod56x36@2": {"2": {**step, "moves": {"green->red": 21}, "limits": {"fit_ft": 21}}}},
        "sized": {"pod56x36@2": 300},
        "room": {
            "pod56x36@2": {"green": 300, "measured": 300, "checks": {}, "size": {
                "lots": 300,
                "width": {"median": 12.0, "under_2": 3},
                "depth": {"median": 8.5, "under_2": 9},
                "both": {"median": 4.25, "under_2": 21},
                "tight": 40,
            }},
            "pod40x30@1": {"green": 12, "measured": 12, "checks": {}},
        },
    }))
    await session.commit()

    page = await client.get("/flats/flags/report")

    assert page.status_code == 200
    size = page.text.split('id="size-pod56x36-2"', 1)[1].split("</table>", 1)[0]
    wider, deeper, both = size.split('class="size-row"')[1:4]
    assert 'data-side="width"' in wider and "Wider" in wider and "12.0 ft" in wider
    assert 'data-side="depth"' in deeper and "8.5 ft" in deeper and 'data-under-2="9"' in deeper
    assert 'data-side="both"' in both and "Both ways at once" in both and "4.2 ft" in both
    tight = page.text.split('id="tight-pod56x36-2"', 1)[1].split("</p>", 1)[0]
    assert 'data-tight="40"' in tight and "300 green lots" in tight
    # A run kept the room on each limit but not each way: it says so.
    old = page.text.split('id="room-pod40x30-1"', 1)[1].split('class="card"', 1)[0]
    assert "before the room each way was kept" in old and 'id="size-' not in old
    narrower, wider = page.text.split('id="sensitivity-pod56x36-2"', 1)[1].split('class="sensitivity-step"')[1:3]
    assert "1 ft narrower" in narrower and "2 ft wider" in wider and 'data-total="3"' in wider
    deep = page.text.split('id="depth-pod56x36-2"', 1)[1].split('class="depth-step"')[2]
    assert "2 ft deeper" in deep and 'data-total="9"' in deep and "9 green → yellow" in deep
    bigger = page.text.split('id="both-pod56x36-2"', 1)[1].split('class="both-step"')
    assert "1 ft smaller both ways" in bigger[1] and 'data-total="0"' in bigger[1]
    assert "2 ft bigger both ways" in bigger[2] and 'data-total="21"' in bigger[2]
