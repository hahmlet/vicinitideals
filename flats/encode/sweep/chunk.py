"""Cut a code document into passages a model can read without losing the line.

Two constraints fight each other here. A chunk has to be small enough that a
model reads all of it rather than the middle of it, and large enough that a
standard is not severed from the sentence that scopes it — "the following apply
in the R-5 zone" three lines above the table it introduces.

The resolution is that chunks break at section boundaries where a document
offers one, and overlap where it does not. An overlap is not redundancy: a
standard split across a boundary is the one kind of miss nothing reports, since
neither chunk contains enough of it to look like a standard at all. Seeing every
line twice, in two different neighbourhoods, is what makes that failure visible.

Every chunk carries the line numbers it came from, because a finding without a
line is not a finding — the whole system quotes ``path#L12`` and a sweep that
returned prose would produce work no one could check.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

#: A line that opens a section. Codifiers are not consistent about which of
#: these they use, and several use two, so the test is deliberately loose: a
#: false boundary costs a slightly short chunk, a missed one costs a severed
#: standard.
_HEADING = re.compile(
    r"""^\s*(?:
        (?:§|Sec(?:tion)?\.?)\s*[\d.]+          # § 4.124 / Sec. 33.110
      | (?:CHAPTER|Chapter|ARTICLE|Article)\s   # Chapter 33.110
      | \d+\.\d+(?:\.\d+)*\s+[A-Z]              # 16.22.020 Development
      | (?:Table|TABLE)\s+[\d.\-]+              # Table 110-7
    )""",
    re.X,
)


@dataclass(frozen=True, slots=True)
class Chunk:
    """One passage of one document, and where in it the passage sits."""

    document: str
    #: 1-indexed and inclusive at both ends, matching how a citation reads.
    first: int
    last: int
    text: str

    @property
    def ref(self) -> str:
        """The citation this chunk covers, in the form the rest of FLATS uses."""
        return f"{self.document}#L{self.first}-L{self.last}"

    def numbered(self) -> str:
        """The text with its real line numbers on it.

        The model is asked to cite a line, and the only way it can name the
        number the rest of the system uses is to be shown it. Numbering from
        one per chunk would produce findings that all point at the top of the
        document.
        """
        return "\n".join(
            f"{n:>6}  {line}" for n, line in enumerate(self.text.splitlines(), self.first)
        )


def boundaries(lines: list[str]) -> set[int]:
    """1-indexed line numbers that open a section."""
    return {n for n, line in enumerate(lines, 1) if _HEADING.match(line)}


def chunks(text: str, *, document: str, size: int = 120, overlap: int = 60) -> list[Chunk]:
    """Cut a document into overlapping passages, preferring section breaks.

    ``size`` and ``overlap`` are in lines rather than tokens on purpose. Line
    numbers are what a citation is made of, and a chunker that counted tokens
    would still have to translate back into lines to say where a finding came
    from — with a rounding error at every boundary.

    An ``overlap`` at or above ``size`` would never advance; it is clamped so a
    caller asking for total coverage gets a slow sweep rather than a hang.
    """
    lines = text.splitlines()
    if not lines:
        return []
    step = max(1, size - min(overlap, size - 1))
    opens = boundaries(lines)

    out: list[Chunk] = []
    at = 1
    while at <= len(lines):
        end = min(at + size - 1, len(lines))
        if end < len(lines):
            # Pull the end back to the last section opening inside the chunk, so
            # the break lands between standards rather than through one. Only
            # worth doing if it leaves a chunk of reasonable size — a heading on
            # the second line would otherwise cut the chunk to nothing.
            near = [n for n in opens if at + size // 2 <= n <= end]
            if near:
                end = max(near) - 1
        out.append(
            Chunk(
                document=document,
                first=at,
                last=end,
                text="\n".join(lines[at - 1 : end]),
            )
        )
        if end >= len(lines):
            break
        at = max(at + step, end - overlap + 1, at + 1)
    return out
