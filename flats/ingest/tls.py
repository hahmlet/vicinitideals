"""The TLS trust the FLATS ingest HTTP clients use: certifi plus pinned extra roots.

Some county servers now chain to a root that Mozilla's list (and so certifi) does
not carry yet. Verification stays on. The extra roots are PEM files under
``flats/config/ca/``, each checked against a SHA-256 fingerprint written here, so
a swapped file fails loudly instead of widening trust. Only the ingest clients
(acquire, probe) take this context; nothing else in the repo does.
"""

from __future__ import annotations

import hashlib
import ssl
from pathlib import Path

import certifi

CA_DIR = Path(__file__).resolve().parents[1] / "config" / "ca"

# file name -> SHA-256 of the certificate (hex, upper case). Both values were
# checked against GoDaddy's repository and CCADB; see the comment in the file.
PINNED_ROOTS: dict[str, str] = {
    "godaddy_tls_root_r1.pem": "25CF3DA8E9B97ADDBF92543C2B82527C8A4E2CFF2062A6483040D4B64ACE719F",
}


def _fingerprint(pem: str) -> str:
    der = ssl.PEM_cert_to_DER_cert(pem[pem.index("-----BEGIN CERTIFICATE-----") :])
    return hashlib.sha256(der).hexdigest().upper()


def ssl_context() -> ssl.SSLContext:
    """A verifying context: certifi's bundle plus every pinned root."""
    ctx = ssl.create_default_context(cafile=certifi.where())
    for name, expected in PINNED_ROOTS.items():
        pem = (CA_DIR / name).read_text(encoding="ascii")
        got = _fingerprint(pem)
        if got != expected:
            raise ssl.SSLError(f"pinned root {name} has fingerprint {got}, expected {expected}")
        ctx.load_verify_locations(cadata=pem[pem.index("-----BEGIN CERTIFICATE-----") :])
    return ctx
