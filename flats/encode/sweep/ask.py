"""Ask a model what a passage requires, and refuse anything it will not cite.

The question is deliberately blind. The model is never shown what FLATS has
already encoded for this jurisdiction, because a model shown an answer agrees
with it — ask "is anything missing here?" beside a list of what we hold and the
reply is a confident all-clear over the exact hole the sweep exists to find. So
it is asked what the passage says, in its own terms, and the comparison happens
in :mod:`flats.encode.sweep.audit`, in code, against the field registry.

Recall is the metric that matters and a model misses standards by not looking
rather than by being small, so each passage is read several times under
different lenses. The lenses are unions, not votes: a standard found once is
kept, and the number of lenses that found it becomes a confidence the queue can
rank by. Nothing here decides anything — a finding is a claim with a line
number on it, which is precisely the shape a person can check in ten seconds.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Callable, Iterable, Protocol

from flats.encode.sweep.chunk import Chunk

#: Where a local model is served. No default host is written into the code: the
#: cluster's address is deployment configuration, and an address in a module is
#: an address that is wrong on every machine but one.
ENDPOINT = os.environ.get("FLATS_OLLAMA_URL", "http://localhost:11434")

#: Small, quantised and already pulled on the box. Overridable per run, because
#: the whole point of the recall score is to decide whether a bigger one earns
#: its wall-clock.
MODEL = os.environ.get("FLATS_SWEEP_MODEL", "qwen2.5:7b")


@dataclass(frozen=True, slots=True)
class Lens:
    """One angle on a passage. Recall comes from asking more than once."""

    key: str
    asks: str


#: Four passes. The first three divide the subject so that no single question
#: has to hold the whole of a zoning chapter in mind; the fourth is the model
#: reading its own answer, which is cheap and reliably turns up the tail.
LENSES: tuple[Lens, ...] = (
    Lens(
        "dimension",
        "requirements about the SIZE, SHAPE or PLACEMENT of a building or its lot "
        "— setbacks, yards, height, stories, lot area, lot width, frontage, lot "
        "depth, building coverage, floor area ratio, density, unit counts, "
        "separation between buildings, open space",
    ),
    Lens(
        "access",
        "requirements about VEHICLES and ACCESS — off-street parking counts, stall "
        "or aisle dimensions, driveway width or placement, garage or vehicle door "
        "setbacks, curb cuts, street frontage or connection, fire or emergency "
        "access, where a building entrance must face",
    ),
    Lens(
        "relief",
        "statements that CHANGE another requirement — exceptions, adjustments, "
        "variances, bonuses, waivers, footnotes, standards that apply only to "
        "certain lot sizes or certain housing types, dates after which something "
        "stops applying, and standards that are set elsewhere by cross-reference",
    ),
)

#: What every lens is told about the building, so that a requirement written for
#: a duplex or a commercial use is not reported as one of ours.
_SUBJECT = (
    "The building being screened is a FOUR-UNIT ATTACHED TOWNHOME (a fourplex / "
    "quadplex, four attached dwelling units), on one lot or on four unit lots, "
    "with its own off-street parking and vehicle access."
)

_PROMPT = """You are reading one passage of a municipal zoning code.

{subject}

List every requirement in this passage that would constrain that building: {asks}.

Rules:
- Report ONLY what this passage itself states. Do not infer, do not generalise,
  do not report a requirement because codes usually have one.
- Every item MUST carry the line number it is stated on, taken from the numbers
  printed at the left of the passage below.
- If the passage states no such requirement, return an empty list. An empty list
  is a correct and common answer.

Return JSON only, no prose, in exactly this shape:
{{"found": [{{"standard": "<short name, e.g. minimum side setback>",
             "applies_to": "<what it applies to, as the passage says it>",
             "states": "<the requirement, e.g. 10 feet / 1 space per unit>",
             "line": <line number>}}]}}

PASSAGE ({document} lines {first}-{last}):
{passage}
"""


class Ask(Protocol):
    """Anything that turns a prompt into text. One method, so a test can be one."""

    def __call__(self, prompt: str) -> str: ...  # pragma: no cover - protocol


@dataclass(frozen=True, slots=True)
class Finding:
    """One requirement a model says a passage states, and where it says it is."""

    document: str
    line: int
    standard: str
    applies_to: str
    states: str
    #: Which lenses turned this up. Length is the confidence, and it is a
    #: confidence in the *reading*, not in the requirement being real.
    lenses: tuple[str, ...] = ()

    @property
    def quote(self) -> str:
        return f"{self.document}#L{self.line}"


class Ollama:
    """A model served by ollama, over HTTP, one prompt at a time.

    Deliberately thin. Retries, pacing and parallelism belong to the run loop,
    which is the thing that knows how much of somebody's GPU it is entitled to.
    """

    def __init__(
        self,
        *,
        endpoint: str = ENDPOINT,
        model: str = MODEL,
        timeout: float = 300.0,
        context: int = 8192,
    ) -> None:
        self.endpoint = endpoint.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.context = context

    def __call__(self, prompt: str) -> str:
        import httpx

        response = httpx.post(
            f"{self.endpoint}/api/generate",
            json={
                "model": self.model,
                "prompt": prompt,
                "stream": False,
                "format": "json",
                "options": {
                    # Extraction, not composition. A model inventing a plausible
                    # setback is the failure this whole sweep is trying to avoid.
                    "temperature": 0.0,
                    "num_ctx": self.context,
                },
            },
            timeout=self.timeout,
        )
        response.raise_for_status()
        return str(response.json().get("response", ""))


def prompt_for(chunk: Chunk, lens: Lens) -> str:
    """The exact text a model is sent for one passage under one lens."""
    return _PROMPT.format(
        subject=_SUBJECT,
        asks=lens.asks,
        document=chunk.document,
        first=chunk.first,
        last=chunk.last,
        passage=chunk.numbered(),
    )


_JSON = re.compile(r"\{.*\}", re.S)


def parse(reply: str, chunk: Chunk, lens: Lens) -> list[Finding]:
    """Findings from one reply, with everything uncheckable dropped.

    A model that returns prose, invents a line outside the passage it was shown,
    or omits the line entirely has produced something nobody can verify, and an
    unverifiable finding in a review queue is worse than no finding — it costs a
    reviewer the same minute and returns nothing.
    """
    match = _JSON.search(reply or "")
    if not match:
        return []
    try:
        raw = json.loads(match.group(0))
    except json.JSONDecodeError:
        return []
    items = raw.get("found") if isinstance(raw, dict) else raw
    if not isinstance(items, list):
        return []

    out: list[Finding] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        try:
            line = int(str(item.get("line", "")).strip())
        except (TypeError, ValueError):
            continue
        if not chunk.first <= line <= chunk.last:
            # Outside the passage it was shown. Either a hallucinated citation
            # or the model numbering from one; both make the line meaningless.
            continue
        standard = str(item.get("standard", "")).strip()[:120]
        if not standard:
            continue
        out.append(
            Finding(
                document=chunk.document,
                line=line,
                standard=standard,
                applies_to=str(item.get("applies_to", "")).strip()[:200],
                states=str(item.get("states", "")).strip()[:200],
                lenses=(lens.key,),
            )
        )
    return out


def merge(found: Iterable[Finding]) -> list[Finding]:
    """One finding per standard per line, carrying every lens that saw it.

    Union rather than intersection. The lenses are asked different questions and
    a standard only one of them thought to ask about is still a standard; what
    the agreement count buys is an order to work the queue in, not a filter.
    """
    seen: dict[tuple[int, str], Finding] = {}
    for one in found:
        key = (one.line, one.standard.lower())
        prior = seen.get(key)
        if prior is None:
            seen[key] = one
            continue
        seen[key] = Finding(
            document=prior.document,
            line=prior.line,
            standard=prior.standard,
            applies_to=prior.applies_to or one.applies_to,
            states=prior.states or one.states,
            lenses=tuple(sorted(set(prior.lenses) | set(one.lenses))),
        )
    return sorted(seen.values(), key=lambda f: (f.line, f.standard.lower()))


def read(chunk: Chunk, ask: Ask, *, lenses: Iterable[Lens] = LENSES) -> list[Finding]:
    """Every requirement the lenses find in one passage."""
    got: list[Finding] = []
    for lens in lenses:
        got.extend(parse(ask(prompt_for(chunk, lens)), chunk, lens))
    return merge(got)


def review_lens(found: list[Finding]) -> Lens | None:
    """The fourth pass: the model reading its own answer for what it left out.

    Built from the findings rather than declared as a constant, because the
    question is "what did you miss", and a model cannot answer that without
    being told what it already said.
    """
    if not found:
        return None
    said = "; ".join(f"line {f.line}: {f.standard}" for f in found[:40])
    return Lens(
        "missed",
        "requirements this passage states that are NOT already in this list, "
        f"which was produced by an earlier reader of the same passage: {said}. "
        "Report only what that list omits",
    )


def sweep(chunk: Chunk, ask: Ask, *, lenses: Iterable[Lens] = LENSES) -> list[Finding]:
    """A passage read under every lens, then re-read for what those missed."""
    found = read(chunk, ask, lenses=lenses)
    second = review_lens(found)
    if second is not None:
        found = merge([*found, *parse(ask(prompt_for(chunk, second)), chunk, second)])
    return found


def scripted(replies: list[str]) -> Callable[[str], str]:
    """An ``Ask`` that returns canned replies in order, then empties.

    Tests need a model that is wrong in specific ways — one that returns prose,
    one that cites a line it was never shown — and a real one cannot be asked to
    be wrong on cue.
    """
    queue = list(replies)

    def ask(prompt: str) -> str:  # noqa: ARG001 — the prompt is the thing under test elsewhere
        return queue.pop(0) if queue else '{"found": []}'

    return ask
