"""`.env.example` must be loadable, because CI loads it and so does a new operator.

The light gate's first step is ``check_promotion_gates``, and the step before
it is ``cp .env.example .env``. So every CI run imports ``app.config`` against
this file. On 2026-06-22 a security fix gave ``inbound_email_org_id`` the type
``UUID | None``; ``.env.example`` writes every unset optional as ``KEY=``, and
pydantic rejects ``""`` for that type. ``Settings()`` raised at import, the
first gate step died, and Ruff, the FLATS firewall, the unit tests and the
FLATS tests -- all of which run after it -- were SKIPPED on every push from
2026-08-14 to 2026-09-03. The run still showed a red X, so nothing looked
different from the run before it, and a syntax error under ``flats/`` rode
through the whole gate into production.

What makes this worth a test rather than a one-line fix is the shape of it. The
example file is the only artefact in the repo that is *executed* by being
copied, and nothing else asserts it parses. Every other optional secret here is
typed ``str``, so an empty line reads as an empty string and no one notices;
the day a second field takes a non-string type, this file breaks again in
exactly the same silent way. This test fails on that day.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ENV_EXAMPLE = Path(__file__).resolve().parents[1] / ".env.example"

#: ``KEY=`` with nothing after it -- how the file spells "not set".
_BLANK = re.compile(r"^([A-Z][A-Z0-9_]*)=\s*$")


def _blank_keys() -> list[str]:
    text = ENV_EXAMPLE.read_text(encoding="utf-8")
    return [m.group(1) for m in (_BLANK.match(ln) for ln in text.splitlines()) if m]


def test_env_example_loads_into_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    """Construct Settings from the example file the way CI does.

    ``env_file`` is passed explicitly rather than by chdir so this does not
    depend on where pytest was invoked from, and every variable the ambient
    environment might supply is cleared for the keys under test -- otherwise a
    developer whose shell already exports one of them would pass a test that
    fails on a clean runner.
    """
    from app.config import Settings

    for key in _blank_keys():
        monkeypatch.delenv(key, raising=False)

    settings = Settings(_env_file=ENV_EXAMPLE)  # type: ignore[call-arg]
    assert settings.inbound_email_org_id is None


def test_every_blank_key_in_env_example_is_actually_optional(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A blank line means unset, so each blank key must read back falsy.

    The first test proves the file loads. This one proves it loads *meaning
    what it says*: a key written ``KEY=`` that arrived as a truthy value would
    be a default leaking in behind an operator who thought they had cleared it.
    """
    from app.config import Settings

    for key in _blank_keys():
        monkeypatch.delenv(key, raising=False)

    settings = Settings(_env_file=ENV_EXAMPLE)  # type: ignore[call-arg]
    for key in _blank_keys():
        field = key.lower()
        if field not in type(settings).model_fields:
            continue
        assert not getattr(settings, field), f"{key} is blank in .env.example but reads truthy"
