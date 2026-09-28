"""Hold pypdf's text extraction at the rules the corpus was read under.

Nearly every PDF in the provenance store was extracted by pypdf 6.15.0.
pypdf 6.16.1 and 6.16.2 changed three lines of extraction, and none of the
changes is neutral for the codifiers' PDFs we read. On Portland's Title 33 and
Gresham's Development Code, layout mode now splits numbers and words that
6.15 kept whole ("9.0801" -> "9 .0 801", "regulations" -> "regulatio ns"),
and plain mode joins a footnote marker onto the line above it ("L/SUR" and
"14" became "L/SUR14"). A drift check then reports each such document as
amended by the city when only the library changed, and a refresh would store
the damaged text and strand the citations that point into it.

So the three lines are held at their 6.15 form here, and nowhere else:

- layout, ``recurse_to_target_op``: the spaces between two text runs are
  counted as ``floor(gap / space width)``. 6.16.2 rounds (py-pdf/pypdf#3992),
  so a gap of half a space, the normal kerning slack inside a word set by
  these publishers, became a space.
- layout, ``TextStateParams.word_tx``: the character spacing ``Tc`` is added
  once per run. 6.16.1 adds it once per character. That is what the PDF spec
  says, but it moves the end of every run and so every gap measured from it.
- plain, ``TextExtraction._handle_tl``: the text leading is scaled by the font
  size and the text matrix. 6.16.2 stops scaling it (py-pdf/pypdf#3987), so
  a line break from T* no longer registers where a superscript sits.

Each patch rewrites one line by exact text. If a later pypdf changes the
line, the rewrite finds nothing and ``held_extraction`` raises rather than
extract under a rule nobody chose. Re-verify the corpus against the new
pypdf (every stored PDF re-extracted and compared) before changing the hold.
"""

from __future__ import annotations

import importlib
import inspect
import textwrap
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from types import FunctionType

#: (module, qualified name, the line pypdf ships, the line the corpus was
#: read under, module globals the held line needs that pypdf no longer imports)
_HELD: tuple[tuple[str, str, str, str, tuple[str, ...]], ...] = (
    (
        "pypdf._text_extraction._layout_mode._fixed_width_page",
        "recurse_to_target_op",
        "spaces = round(excess_tx / _tj.space_tx) if excess_tx > 0 else 0",
        "spaces = int(excess_tx // _tj.space_tx) if _tj.space_tx else 0",
        (),
    ),
    (
        "pypdf._text_extraction._layout_mode._text_state_params",
        "TextStateParams.word_tx",
        "+ len(word) * self.Tc",
        "+ self.Tc",
        (),
    ),
    (
        "pypdf._text_extraction._text_extractor",
        "TextExtraction._handle_tl",
        "self.TL = float(operands[0] if operands else 0.0)\n",
        "scale_x = math.sqrt(self.tm_matrix[0] ** 2 + self.tm_matrix[2] ** 2)\n"
        "    self.TL = float(operands[0] if operands else 0.0) * self.font_size * scale_x\n",
        ("math",),
    ),
)

_lock = threading.Lock()
_compiled: list[tuple[object, str, object, object]] | None = None


def _rewrite(
    module_name: str, qualname: str, shipped: str, held: str, needs: tuple[str, ...]
) -> tuple[object, str, object, object]:
    module = importlib.import_module(module_name)
    owner: object = module
    *path, name = qualname.split(".")
    for part in path:
        owner = getattr(owner, part)
    original = getattr(owner, name)
    source = textwrap.dedent(inspect.getsource(original))
    if source.count(shipped) != 1:
        raise RuntimeError(
            f"pypdf {qualname} no longer carries the line held by "
            f"flats.provenance.pdf_hold ({shipped.strip()!r}); re-verify the "
            "stored corpus against this pypdf before changing the hold"
        )
    for needed in needs:
        module.__dict__.setdefault(needed, importlib.import_module(needed))
    namespace: dict[str, object] = {}
    code = compile(source.replace(shipped, held), inspect.getsourcefile(original) or "", "exec")
    # pypdf's own source with one line changed, run in pypdf's own module
    # namespace so every other name resolves exactly as it would unpatched.
    exec(code, module.__dict__, namespace)  # noqa: S102
    replacement = namespace[name]
    if isinstance(replacement, FunctionType) and isinstance(original, FunctionType):
        replacement.__qualname__ = original.__qualname__
    return owner, name, original, replacement


def _patches() -> list[tuple[object, str, object, object]]:
    global _compiled
    if _compiled is None:
        _compiled = [_rewrite(*held) for held in _HELD]
    return _compiled


@contextmanager
def held_extraction() -> Iterator[None]:
    """Extract inside this block and pypdf reads text as 6.15 did.

    Held for the length of the block only, under a lock: the patches are
    module attributes, so two extractions must not interleave with a third
    caller that expects pypdf's own behaviour.
    """
    with _lock:
        patches = _patches()
        for owner, name, _, replacement in patches:
            setattr(owner, name, replacement)
        try:
            yield
        finally:
            for owner, name, original, _ in patches:
                setattr(owner, name, original)
