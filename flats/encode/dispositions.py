"""What we decided about each captured footnote, and what happens by default.

The census pulls every footnote out of every stored document without judging
any of them. This is where judgement is recorded -- and the default is the
whole point: a footnote nobody has ruled on is ``unread``, and ``unread``
blocks. Not a warning, not a log line. A standard whose region contains an
unread footnote is not something we get to call GREEN, because the note may
be the sentence that halves the number.

Three states, and only one of them is silent by omission:

``unread``
    Captured, nobody has decided. Blocks. This is what every footnote is
    until someone writes it down.
``encoded``
    Turned into a rule. Carries the zone and field it became, so the claim is
    checkable against the encoding rather than taken on trust.
``dismissed``
    Ruled irrelevant, with a reason in writing. Reasons are shared on purpose:
    "detached dwellings only" said forty times is a class, and deleting that
    one reason returns all forty footnotes to ``unread`` at once. That is the
    rejection pass being re-runnable rather than a decision nobody can revisit.
``unmeasured``
    Read, understood, and it turns on something about the lot that nothing
    computes yet. Oregon City prints "public utility easements may supersede
    the minimum setback" under every dimensional table in Title 17; the
    sentence is plain, and no easement layer is held. This is not the same as
    unread and collapsing the two costs in both directions -- leaving it
    unread says nobody looked, which stops the value ever being signed, while
    dismissing it says the sentence does not matter, which is false and
    produces a GREEN a surveyor would not.

    So it stops blocking the *encoding* and goes on capping the *verdict*: the
    ruling must name a registered site fact, and a site fact registered with
    no assumption can never produce a GREEN. The gap moves from "somebody has
    to read this" to "somebody has to buy this data", which is a different
    queue and a truer one.

Dispositions bind to the footnote's *text*, not to its line number. A stored
document that gets re-fetched moves its lines, and a codifier who amends a
note changes what we ruled on. So each entry carries a digest of the text it
was written against: the line may move and the ruling follows it, but if the
words change the ruling evaporates and the footnote is ``unread`` again. A
disposition is a statement about a sentence, and it should not outlive the
sentence.

Run it::

    uv run python -m flats.encode.dispositions
    uv run python -m flats.encode.dispositions --layer or/multnomah/gresham
    uv run python -m flats.encode.dispositions --queue
"""

from __future__ import annotations

import hashlib
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import yaml

from flats.encode.footnotes import Body, Census, survey
from flats.rules.conditions import condition

CONFIG_ROOT = Path(__file__).resolve().parents[1] / "config" / "footnotes"

#: The states a footnote can be in. ``unread`` is not written anywhere -- it
#: is what a footnote is when nothing says otherwise, which is what makes the
#: default safe rather than a thing somebody has to remember to set.
STATES = ("unread", "encoded", "dismissed", "unmeasured")

#: The states a file may declare. ``unread`` is what a footnote is when
#: nothing says otherwise.
DECIDED = ("encoded", "dismissed", "unmeasured")

_SPACE = re.compile(r"\s+")


def digest(text: str) -> str:
    """A stable fingerprint of a footnote's words.

    Whitespace is collapsed and case dropped, because extraction re-flows both
    and neither changes what the note says. Nothing else is normalised: a
    codifier who edits a word has edited the rule, and the disposition written
    against the old wording should not survive it.
    """
    normalised = _SPACE.sub(" ", text).strip().lower()
    return hashlib.sha1(normalised.encode("utf-8")).hexdigest()[:12]


class DispositionError(Exception):
    """A disposition file that cannot be trusted to mean what it says."""


@dataclass(frozen=True, slots=True)
class Ruling:
    """One recorded decision, as written in the YAML."""

    layer: str
    digest: str
    state: str
    reason: str = ""
    encoded_as: str = ""
    #: For ``unmeasured``: the registered site fact this note turns on.
    fact: str = ""
    quote: str = ""


@dataclass(frozen=True, slots=True)
class Note:
    """One captured footnote joined to whatever was decided about it."""

    layer: str
    doc: str
    line: int
    #: As the codifier printed it -- "1", "12", "A".
    mark: str
    text: str
    state: str
    reason: str = ""
    encoded_as: str = ""
    #: For ``unmeasured``: the registered site fact this note turns on.
    fact: str = ""
    #: Set when a ruling was found for this note's line but not its words --
    #: the codifier amended it, so the ruling no longer applies.
    amended: bool = False

    @property
    def quote(self) -> str:
        return f"{self.doc}#L{self.line}"

    @property
    def blocking(self) -> bool:
        """Whether this note stops the value under it being signed."""
        return self.state == "unread"

    @property
    def caps_green(self) -> bool:
        """Whether a lot under this note can be called GREEN.

        Two states say no for opposite reasons: nobody has read the note, or
        somebody read it and it turns on a fact about the lot that nothing
        measures. Verification can clear the first. Only data clears the
        second.
        """
        return self.state in ("unread", "unmeasured")


def _adopts(raw: dict, path: Path) -> list[str]:
    """Layers whose rulings this file takes as its own.

    Two jurisdictions can store the same chapter. Multnomah County's R10, R20,
    RF and R7 are Portland-administered pockets, and the layer's 33.110.txt is
    PCC 33.110 -- the same sentences, fetched twice, digesting identically. A
    ruling is a statement about a sentence, so the second copy does not need
    fifteen re-typed reasons that will drift from the first fifteen.

    Not a default and not inferred from a shared digest: adopting another
    jurisdiction's judgement is a claim that its reasons hold here, and it is
    written down with the reason it holds. The adopting file's own rulings win
    where both speak, which is how a pocket that reads a note differently says
    so.
    """
    raw_adopts = raw.get("adopts") or []
    if not isinstance(raw_adopts, list):
        raise DispositionError(f"{path}: 'adopts' must be a list")
    out: list[str] = []
    for i, entry in enumerate(raw_adopts):
        where = f"{path}: adopts[{i}]"
        if not isinstance(entry, dict):
            raise DispositionError(f"{where}: expected a mapping with 'layer' and 'reason'")
        adopted = str(entry.get("layer", "")).strip()
        if not adopted:
            raise DispositionError(f"{where}: name the layer whose rulings this file adopts")
        if not str(entry.get("reason", "")).strip():
            raise DispositionError(
                f"{where}: say why another jurisdiction's reasons hold here"
            )
        out.append(adopted)
    return out


def _read(path: Path) -> list[Ruling]:
    """One jurisdiction's rulings, refusing anything it cannot vouch for."""
    layer = path.relative_to(CONFIG_ROOT).with_suffix("").as_posix()
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    entries = raw.get("notes") or []
    if not isinstance(entries, list):
        raise DispositionError(f"{path}: 'notes' must be a list")
    out: list[Ruling] = []
    for i, entry in enumerate(entries):
        where = f"{path}: notes[{i}]"
        if not isinstance(entry, dict):
            raise DispositionError(f"{where}: expected a mapping")
        state = entry.get("state", "")
        if state not in DECIDED:
            raise DispositionError(
                f"{where}: state must be one of {', '.join(repr(s) for s in DECIDED)}; "
                "'unread' is the default and is never written down"
            )
        text_digest = str(entry.get("digest", "")).strip()
        if not text_digest:
            raise DispositionError(f"{where}: a ruling without a digest cannot be matched")
        if state == "dismissed" and not str(entry.get("reason", "")).strip():
            raise DispositionError(
                f"{where}: a dismissal without a reason is an omission with extra steps"
            )
        if state == "encoded" and not str(entry.get("encoded_as", "")).strip():
            raise DispositionError(
                f"{where}: 'encoded' has to name what it became, or it cannot be checked"
            )
        fact = str(entry.get("fact", "")).strip()
        if state == "unmeasured":
            if not str(entry.get("reason", "")).strip():
                raise DispositionError(
                    f"{where}: 'unmeasured' states what the note turns on, in words"
                )
            try:
                registered = condition(fact)
            except KeyError as exc:
                # An unregistered fact is a gap nobody can act on: no screen
                # would ever look for it and no data layer would be bought for
                # it. Registering it is the first half of the work.
                raise DispositionError(f"{where}: {exc.args[0]}") from None
            if registered.kind != "site_fact":
                raise DispositionError(
                    f"{where}: 'fact' names {fact!r}, which is a {registered.kind}; "
                    "an unmeasured footnote turns on something about the lot"
                )
            if registered.assume is not None:
                # A fact with an assumption is one the screen answers by
                # default, so a note resting on it is not unmeasured -- it is
                # a variant somebody has to encode.
                raise DispositionError(
                    f"{where}: {fact!r} is assumed {registered.assume} across a batch, "
                    "so this note is encodable rather than unmeasured"
                )
        out.append(
            Ruling(
                layer=layer,
                digest=text_digest,
                state=state,
                reason=str(entry.get("reason", "")).strip(),
                encoded_as=str(entry.get("encoded_as", "")).strip(),
                fact=fact,
                quote=str(entry.get("quote", "")).strip(),
            )
        )
    return out


def rulings() -> dict[str, list[Ruling]]:
    """Every recorded decision, keyed by layer, adoptions resolved."""
    own: dict[str, list[Ruling]] = {}
    adopts: dict[str, list[str]] = {}
    if not CONFIG_ROOT.is_dir():
        return own
    for path in sorted(CONFIG_ROOT.rglob("*.yaml")):
        layer = path.relative_to(CONFIG_ROOT).with_suffix("").as_posix()
        own.setdefault(layer, [])
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        adopts[layer] = _adopts(raw if isinstance(raw, dict) else {}, path)
        for ruling in _read(path):
            own.setdefault(ruling.layer, []).append(ruling)

    out: dict[str, list[Ruling]] = {}
    for layer, mine in own.items():
        inherited: list[Ruling] = []
        for source in adopts.get(layer, ()):
            if source not in own:
                # A typo here would adopt nothing and read as a jurisdiction
                # whose notes were all ruled on, which is the one failure this
                # whole register exists to make impossible.
                raise DispositionError(
                    f"{layer}: adopts {source!r}, which has no rulings file"
                )
            if adopts.get(source):
                # One hop. A chain would make "who ruled on this" a graph walk,
                # and the answer to that question has to fit in a sentence.
                raise DispositionError(
                    f"{layer}: adopts {source!r}, which itself adopts — "
                    "name the original instead"
                )
            inherited.extend(own[source])
        # Own rulings last: where both speak, the file that names this layer
        # wins.
        out[layer] = inherited + mine
    return out


def _join(census: Census, decided: Sequence[Ruling]) -> list[Note]:
    by_digest = {r.digest: r for r in decided}
    by_quote = {r.quote: r for r in decided if r.quote}
    notes: list[Note] = []
    for body in census.bodies:
        notes.append(_note(census.layer, body, by_digest, by_quote))
    return notes


def _note(
    layer: str,
    body: Body,
    by_digest: dict[str, Ruling],
    by_quote: dict[str, Ruling],
) -> Note:
    ruling = by_digest.get(digest(body.text))
    if ruling is not None:
        return Note(
            layer=layer,
            doc=body.doc,
            line=body.line,
            mark=body.mark,
            text=body.text,
            state=ruling.state,
            reason=ruling.reason,
            encoded_as=ruling.encoded_as,
            fact=ruling.fact,
        )
    # A ruling written against this line whose words no longer match it. The
    # note was amended, so the decision is void and this is a fresh footnote.
    stale = by_quote.get(body.quote)
    return Note(
        layer=layer,
        doc=body.doc,
        line=body.line,
        mark=body.mark,
        text=body.text,
        state="unread",
        amended=stale is not None,
    )


def notes(layer: str | None = None) -> list[Note]:
    """Every captured footnote with its state, over the store or one layer."""
    decided = rulings()
    out: list[Note] = []
    for census in survey(layer):
        out.extend(_join(census, decided.get(census.layer, [])))
    return out


def by_state(rows: Sequence[Note]) -> dict[str, int]:
    counts = {state: 0 for state in STATES}
    for row in rows:
        counts[row.state] += 1
    return {k: v for k, v in counts.items() if v}


def render(rows: Sequence[Note], *, queue: bool = False) -> str:
    """The register as text, for a terminal or a commit message."""
    if queue:
        blocking = [r for r in rows if r.blocking]
        lines = [
            f"{r.quote:<52} #{r.mark:<3} {'AMENDED ' if r.amended else ''}{r.text[:90]}"
            for r in blocking
        ]
        lines.append("")
        lines.append(f"unread={len(blocking)} of {len(rows)} captured")
        return "\n".join(lines)

    per_layer: dict[str, list[Note]] = {}
    for row in rows:
        per_layer.setdefault(row.layer, []).append(row)
    width = max((len(k) for k in per_layer), default=20)
    lines = []
    for layer, group in sorted(per_layer.items()):
        tally = by_state(group)
        lines.append(
            f"{layer:<{width}}  {len(group):>3} footnotes  "
            + "  ".join(f"{k}={v}" for k, v in tally.items())
        )
    lines.append("")
    tally = by_state(rows)
    lines.append(
        f"captured={len(rows)}  "
        + "  ".join(f"{k}={v}" for k, v in tally.items())
        + f"  blocking={sum(1 for r in rows if r.blocking)}"
        + f"  caps_green={sum(1 for r in rows if r.caps_green)}"
    )
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    layer = args[args.index("--layer") + 1] if "--layer" in args else None
    print(render(notes(layer), queue="--queue" in args))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())


__all__ = [
    "CONFIG_ROOT",
    "DispositionError",
    "Note",
    "Ruling",
    "STATES",
    "by_state",
    "digest",
    "notes",
    "render",
    "rulings",
]
