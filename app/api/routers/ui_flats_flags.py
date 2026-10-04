"""Approve the flag plan's numbers: every kind of unknown, and the colour rule.

Steph's flag plan splits what we do not know (a *flag*) from what we know
blocks (a *bind*), and makes the numbers that turn flags into a colour a
person's to set: each flag type's risk, severity, how it gets resolved and
when to work it, and the rule set's line between green and yellow. An agent
only proposes them -- ``status: pending`` in ``flats/config/flags.yaml`` and
``colour.yaml`` -- and a pending type counts at its proposed values.

This page is where they get set. A decision is a row in
``flats.flag_decisions``; it is not in force until
``scripts/flats_drain_flag_decisions.py`` writes it into the files for commit,
and the page says which decisions are waiting for that. Anyone signed in may
look; only the owner may decide.

Kinds waiting for approval sit at the top. There is no deadline on them
(Steph 2026-10-03): a kind nobody approved keeps its lots at its proposed
severity, which is the cautious default.

Registered ahead of ``ui_flats``: that router ends in a catch-all
``/flats/{layer_id:path}`` that would otherwise swallow ``/flats/flags``.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select

from app.api.deps import DBSession
from app.api.routers.ui_helpers import _base_ctx, _get_counts, _get_user, templates
from app.models.flats import RULES_SUBJECT, FlatsFlagDecision
from app.models.org import User
from app.services import flats_flags as flag_store
from flats.score import flags as fp

router = APIRouter(include_in_schema=False)

#: The resolution types in the order the page lists them: measurement first,
#: because it is the preferred way to close a flag (Steph 2026-10-03: the
#: other three are "the failure mode").
RESOLUTION_WORDS = {
    "measurement": "We measure it (maps and data)",
    "document_review": "Someone reads the code or documents",
    "external_inquiry": "Ask the city",
    "per_lot_review": "Someone checks each lot",
}
RISK_WORDS = {
    "remote": "Remote",
    "unlikely": "Unlikely",
    "possible": "Possible",
    "likely": "Likely",
    "near_certain": "Near certain",
}
PRIORITY_WORDS = {"now": "Now", "next": "Next", "later": "Later", "parked": "Parked"}
SCOPE_WORDS = {
    "shared": "One answer covers every lot it touches",
    "per_lot": "Each lot answered on its own",
}
ABSORB_WORDS = {
    "": "Nothing",
    "footprint_width": "Building width",
    "footprint_depth": "Building depth",
    "height": "Height",
    "stories": "Stories",
    "units": "Number of units",
    "parking": "Parking",
    "ground_story": "Ground floor",
}
_RES_ORDER = {r: i for i, r in enumerate(RESOLUTION_WORDS)}


def _owner(user: User | None) -> bool:
    return bool(user and user.is_admin)


async def _waiting(session: DBSession) -> dict[str, FlatsFlagDecision]:
    """The latest undrained decision per subject: approved, not yet in force."""
    rows = (
        await session.execute(
            select(FlatsFlagDecision)
            .where(FlatsFlagDecision.exported_at.is_(None))
            .order_by(FlatsFlagDecision.decided_at, FlatsFlagDecision.id)
        )
    ).scalars().all()
    return {row.subject: row for row in rows}


def _type_row(t: fp.FlagType, waiting: FlatsFlagDecision | None) -> dict[str, Any]:
    shown = {name: getattr(t, name) for name in fp.TYPE_DECIDED}
    shown = {k: getattr(v, "value", v) for k, v in shown.items()}
    if waiting is not None:
        shown.update(waiting.values)
        state = "waiting"
    elif t.status is fp.TypeStatus.approved:
        state = "approved"
    else:
        state = "proposed"
    return {
        "code": t.code,
        "description": t.description,
        "path": t.path,
        "scope": SCOPE_WORDS[t.scope.value],
        "state": state,
        "values": shown,
        "approved_by": waiting.decided_by if waiting is not None else t.approved_by,
        "approved_on": (
            waiting.decided_at.date() if waiting is not None else t.approved_on
        ),
    }


def _rules_view(rules: fp.ColourRules, waiting: FlatsFlagDecision | None) -> dict[str, Any]:
    values: dict[str, Any] = {
        "yellow_at_severity": rules.yellow_at_severity,
        "approval_severity": rules.approval_severity,
        "near_miss": {k: v for k, v in rules.near_miss.items()},
        "near_miss_severity": rules.near_miss_severity,
        "risk_bands": {getattr(k, "value", k): v for k, v in rules.risk_bands.items()},
    }
    if waiting is not None:
        for key, value in waiting.values.items():
            values[key] = {**values[key], **value} if isinstance(value, dict) else value
        state = "waiting"
    elif rules.status is fp.TypeStatus.approved:
        state = "approved"
    else:
        state = "proposed"
    return {
        "state": state,
        "values": values,
        "approved_by": waiting.decided_by if waiting is not None else rules.approved_by,
        "approved_on": waiting.decided_at.date() if waiting is not None else rules.approved_on,
    }


def _ctx_words() -> dict[str, Any]:
    return {
        "resolution_words": RESOLUTION_WORDS,
        "risk_words": RISK_WORDS,
        "priority_words": PRIORITY_WORDS,
        "absorb_words": ABSORB_WORDS,
    }


@router.get("/flats/flags", response_class=HTMLResponse)
async def flats_flags(request: Request, session: DBSession) -> HTMLResponse:
    """Every kind of unknown, the numbers it carries, and the colour rule."""
    user = await _get_user(session, request)
    dedup_count, conflicts_count = await _get_counts(session)
    waiting = await _waiting(session)
    reg = fp.load_registry()
    rules = fp.load_rules()
    state_order = {"proposed": 0, "waiting": 1, "approved": 2}
    rows = sorted(
        (_type_row(t, waiting.get(t.code)) for t in reg),
        key=lambda r: (
            state_order[r["state"]],
            _RES_ORDER[r["values"]["resolution"]],
            r["code"],
        ),
    )
    by_resolution = {r: 0 for r in RESOLUTION_WORDS}
    for r in rows:
        by_resolution[r["values"]["resolution"]] += 1
    # How many lots each kind holds open now, by colour (the plan's
    # population, counted live from the flag history).
    held = await flag_store.open_counts(session)
    for r in rows:
        r["open"] = held.get(r["code"], {})
    waiting_questions = len(await flag_store.questions(session, answered=False))
    ctx = {
        **_base_ctx(user, dedup_count, "flats_flags", conflicts_count=conflicts_count),
        **_ctx_words(),
        "rows": rows,
        "rules": _rules_view(rules, waiting.get(RULES_SUBJECT)),
        "owner": _owner(user),
        "counts": {
            "total": len(rows),
            "proposed": sum(r["state"] == "proposed" for r in rows),
            "waiting": sum(r["state"] == "waiting" for r in rows) + (RULES_SUBJECT in waiting),
            "approved": sum(r["state"] == "approved" for r in rows),
        },
        "by_resolution": by_resolution,
        "waiting_questions": waiting_questions,
    }
    return templates.TemplateResponse(request, "flats_flags.html", ctx)


@router.get("/flats/flags/questions", response_class=HTMLResponse)
async def flats_flag_questions(request: Request, session: DBSession) -> HTMLResponse:
    """The review queue: questions an agent could not answer alone, each on
    one flag's key, with the lots that key holds open now."""
    user = await _get_user(session, request)
    dedup_count, conflicts_count = await _get_counts(session)
    reg = fp.registry()

    def shown(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        out = []
        for item in items:
            q = item["row"]
            kind = reg.types.get(q.code)
            out.append(
                {
                    "q": q,
                    "what": kind.description if kind is not None else q.code,
                    "key": q.key.replace(fp.SEP, " · "),
                    "lots": item["lots"],
                    "total": sum(item["lots"].values()),
                }
            )
        return out

    ctx = {
        **_base_ctx(user, dedup_count, "flats_flags", conflicts_count=conflicts_count),
        "waiting": shown(await flag_store.questions(session, answered=False)),
        "answered": shown(await flag_store.questions(session, answered=True)),
        "owner": _owner(user),
        "error": request.query_params.get("error", ""),
    }
    return templates.TemplateResponse(request, "flats_flag_questions.html", ctx)


@router.get("/flats/flags/queue", response_class=HTMLResponse)
async def flats_flag_queue(request: Request, session: DBSession) -> HTMLResponse:
    """The work queue: open questions by priority, then by how many lots an
    answer would turn green on its own, then by how many it holds yellow."""
    user = await _get_user(session, request)
    dedup_count, conflicts_count = await _get_counts(session)
    ctx = {
        **_base_ctx(user, dedup_count, "flats_flags", conflicts_count=conflicts_count),
        **_ctx_words(),
        "scope_words": SCOPE_WORDS,
        "queue": await flag_store.work_queue(session),
    }
    return templates.TemplateResponse(request, "flats_flag_queue.html", ctx)


#: How the report names a width step.
def _step_words(step: str) -> str:
    n = float(step)
    feet = f"{abs(n):g} ft"
    return f"{feet} wider" if n > 0 else f"{feet} narrower"


@router.get("/flats/flags/report", response_class=HTMLResponse)
async def flats_flag_report(request: Request, session: DBSession) -> HTMLResponse:
    """The newest nightly check and the design sensitivity report."""
    user = await _get_user(session, request)
    dedup_count, conflicts_count = await _get_counts(session)
    row = await flag_store.latest_report(session)
    sensitivity = []
    if row is not None:
        for design, per in sorted((row.report.get("sensitivity") or {}).items()):
            steps = []
            for step in row.report.get("steps") or []:
                s = per.get(str(step)) or {"moves": {}, "examples": [], "keys": {}}
                steps.append(
                    {
                        "words": _step_words(str(step)),
                        "moves": s["moves"],
                        "total": sum(s["moves"].values()),
                        "examples": s["examples"],
                        "questions": [(k.replace(fp.SEP, " · ").rstrip(" ·"), n) for k, n in s["keys"].items()],
                    }
                )
            sensitivity.append({"design": design, "steps": steps})
    ctx = {
        **_base_ctx(user, dedup_count, "flats_flags", conflicts_count=conflicts_count),
        "report": row,
        "r": row.report if row is not None else {},
        "sensitivity": sensitivity,
    }
    return templates.TemplateResponse(request, "flats_flag_report.html", ctx)


@router.post("/ui/flats/flags/questions/{question_id}/answer", response_class=HTMLResponse)
async def flats_flag_question_answer(
    request: Request,
    session: DBSession,
    question_id: int,
    answer: str = Form(""),
) -> HTMLResponse:
    """A person's answer to a waiting question. The answer is a note for
    whoever encodes the confirmed value; the flag closes when the screen,
    reading it, stops raising it."""
    user = await _get_user(session, request)
    if user is None:
        return HTMLResponse("sign in first", status_code=401)
    if not _owner(user):
        return HTMLResponse("only the owner answers these", status_code=403)
    try:
        await flag_store.answer(session, question_id, text_=answer, by=user.name, user_id=user.id)
    except flag_store.FlagWriteError as exc:
        await session.rollback()
        return RedirectResponse(f"/flats/flags/questions?error={quote(str(exc)[:200])}", status_code=303)
    await session.commit()
    return RedirectResponse("/flats/flags/questions", status_code=303)


@router.post("/ui/flats/flags/type", response_class=HTMLResponse)
async def flats_flags_decide_type(
    request: Request,
    session: DBSession,
    code: str = Form(...),
    risk: str = Form(...),
    severity: int = Form(...),
    absorbs: str = Form(""),
    resolution: str = Form(...),
    priority: str = Form(...),
    note: str = Form(""),
) -> HTMLResponse:
    """Approve one kind of unknown at the numbers on its row."""
    user = await _get_user(session, request)
    if user is None:
        return HTMLResponse("sign in first", status_code=401)
    if not _owner(user):
        return HTMLResponse("only the owner approves these", status_code=403)
    reg = fp.load_registry()
    if code not in reg:
        return HTMLResponse("no such kind of unknown", status_code=404)
    values = {
        "risk": risk,
        "severity": severity,
        "absorbs": absorbs or None,
        "resolution": resolution,
        "priority": priority,
    }
    current = reg[code]
    error = ""
    try:
        # The file's own validation, before anything is stored: a decision
        # the drain could not write must not sit in the queue as if it could.
        fp.FlagType(**{**current.model_dump(), **values})
    except ValueError as exc:
        error = str(exc).splitlines()[0]
    if not error:
        row = FlatsFlagDecision(
            subject=code,
            values=values,
            note=note.strip()[:2000],
            decided_by=user.name[:200],
            decided_user_id=user.id,
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)
        waiting = row
    else:
        waiting = (await _waiting(session)).get(code)
    ctx = {
        **_ctx_words(),
        "row": _type_row(current, waiting),
        "owner": True,
        "error": error,
        "said": "" if error else "Approved -- in force at the next write-in",
    }
    return templates.TemplateResponse(request, "partials/flats_flag_row.html", ctx)


@router.post("/ui/flats/flags/rules", response_class=HTMLResponse)
async def flats_flags_decide_rules(
    request: Request,
    session: DBSession,
    yellow_at_severity: int = Form(...),
    approval_severity: int = Form(...),
    near_miss_fit_ft: float = Form(...),
    near_miss_severity: int = Form(...),
    risk_remote: float = Form(...),
    risk_unlikely: float = Form(...),
    risk_possible: float = Form(...),
    risk_likely: float = Form(...),
    risk_near_certain: float = Form(...),
    note: str = Form(""),
) -> HTMLResponse:
    """Approve the colour rule at the numbers in its form."""
    user = await _get_user(session, request)
    if user is None:
        return HTMLResponse("sign in first", status_code=401)
    if not _owner(user):
        return HTMLResponse("only the owner approves these", status_code=403)
    values: dict[str, Any] = {
        "yellow_at_severity": yellow_at_severity,
        "approval_severity": approval_severity,
        "near_miss": {"fit_ft": near_miss_fit_ft},
        "near_miss_severity": near_miss_severity,
        # The form asks in percent, the file holds a probability.
        "risk_bands": {
            "remote": round(risk_remote / 100, 4),
            "unlikely": round(risk_unlikely / 100, 4),
            "possible": round(risk_possible / 100, 4),
            "likely": round(risk_likely / 100, 4),
            "near_certain": round(risk_near_certain / 100, 4),
        },
    }
    rules = fp.load_rules()
    error = ""
    try:
        merged = rules.model_dump()
        for key, value in values.items():
            merged[key] = {**merged[key], **value} if isinstance(value, dict) else value
        fp.ColourRules(**merged)
    except ValueError as exc:
        error = str(exc).splitlines()[0]
    if not error:
        row = FlatsFlagDecision(
            subject=RULES_SUBJECT,
            values=values,
            note=note.strip()[:2000],
            decided_by=user.name[:200],
            decided_user_id=user.id,
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)
        waiting = row
    else:
        waiting = (await _waiting(session)).get(RULES_SUBJECT)
    ctx = {
        **_ctx_words(),
        "rules": _rules_view(rules, waiting),
        "owner": True,
        "error": error,
        "said": "" if error else "Approved -- in force at the next write-in",
    }
    return templates.TemplateResponse(request, "partials/flats_flag_rules.html", ctx)
