"""The ingest HTTP clients trust certifi plus the pinned extra roots, offline.

No network: the context's loaded CA certificates are compared with certifi's
bundle and the pinned PEM, and a tampered pin is refused.
"""

from __future__ import annotations

import ssl
from pathlib import Path

import certifi
import httpx
import pytest

from flats.ingest import tls

pytestmark = pytest.mark.unit

GODADDY_R1_SHA256 = "25CF3DA8E9B97ADDBF92543C2B82527C8A4E2CFF2062A6483040D4B64ACE719F"


def _subjects(ctx: ssl.SSLContext) -> set[str]:
    return {f"{k}={v}" for c in ctx.get_ca_certs() for rdn in c["subject"] for k, v in rdn}


def test_context_verifies_and_trusts_certifi_plus_pinned_root() -> None:
    ctx = tls.ssl_context()
    assert ctx.verify_mode == ssl.CERT_REQUIRED and ctx.check_hostname
    base = ssl.create_default_context(cafile=certifi.where())
    assert _subjects(base) <= _subjects(ctx)  # nothing certifi trusts is lost
    assert "commonName=GoDaddy TLS Root CA - R1" in _subjects(ctx)
    assert "commonName=GoDaddy TLS Root CA - R1" not in _subjects(base)  # why the pin exists
    assert len(ctx.get_ca_certs()) == len(base.get_ca_certs()) + len(tls.PINNED_ROOTS)


def test_pin_matches_the_fingerprint_recorded_from_two_sources() -> None:
    assert tls.PINNED_ROOTS["godaddy_tls_root_r1.pem"] == GODADDY_R1_SHA256
    pem = (tls.CA_DIR / "godaddy_tls_root_r1.pem").read_text(encoding="ascii")
    assert tls._fingerprint(pem) == GODADDY_R1_SHA256


def test_a_swapped_pin_is_refused(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    pem = (tls.CA_DIR / "godaddy_tls_root_r1.pem").read_text(encoding="ascii")
    monkeypatch.setattr(tls, "CA_DIR", tmp_path)
    monkeypatch.setattr(tls, "PINNED_ROOTS", {"x.pem": "00" * 32})
    (tmp_path / "x.pem").write_text(pem, encoding="ascii")
    with pytest.raises(ssl.SSLError, match="fingerprint"):
        tls.ssl_context()


def test_default_ingest_clients_use_the_context(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    seen: list[object] = []
    real = httpx.Client

    def spy(*a: object, **kw: object) -> httpx.Client:
        seen.append(kw.get("verify"))
        return real(*a, **kw)

    monkeypatch.setattr(httpx, "Client", spy)
    from flats.ingest import acquire as stage
    from flats.ingest import probe
    from flats.ingest.sources import load_pipeline

    pipeline = load_pipeline()
    stage.acquire(pipeline, tmp_path / "s", keys=[], log=lambda _m: None)
    probe.probe(pipeline, {"datasets": {}}, log=lambda _m: None)
    assert len(seen) == 2 and all(isinstance(v, ssl.SSLContext) for v in seen)
