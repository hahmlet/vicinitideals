"""Standalone LibreOffice recalc — run via system python3 (has uno).

LibreOffice's ``soffice --convert-to xlsx`` does not write cached
formula values back into the .xlsx output, so ``openpyxl.load_workbook
(..., data_only=True)`` returns ``None`` for every formula cell after
that conversion. The fix is to use UNO directly:

  1. Open the workbook
  2. ``calculateAll()``
  3. Save via ``storeToURL`` with the ``Calc Office Open XML`` filter

This module is invoked as a subprocess by
``_parity_helpers.recalc_with_libreoffice``. It cannot be imported
from the uv venv because ``uno`` is only available under the system
``python3`` (provided by the ``python3-uno`` package).

Args (positional):
    1: path to the workbook to recalc (in place)
    2: UNO connection URL — e.g. ``pipe,name=parity-abc;urp;``

Exit codes:
    0 — success
    1 — uno import / connect / open / save failed (stderr has details)
"""
from __future__ import annotations

import os
import sys
import time


def _prop(name, value):
    from com.sun.star.beans import PropertyValue
    p = PropertyValue()
    p.Name = name
    p.Value = value
    return p


def _to_file_url(path: str) -> str:
    abs_path = os.path.abspath(path)
    # uno requires file:// URLs; pathlib's as_uri() handles spaces.
    from pathlib import Path
    return Path(abs_path).as_uri()


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        print(
            "usage: lo_recalc.py <xlsx-path> <uno-connect-string>",
            file=sys.stderr,
        )
        return 1

    target_path = argv[1]
    connect = argv[2]

    try:
        import uno  # type: ignore[import-not-found]
    except ImportError as exc:
        print(f"uno import failed: {exc!r}", file=sys.stderr)
        return 1

    # Retry the resolver — soffice may still be opening the pipe when
    # we get here. 0.25s × 60 = 15s total wait, plenty for a cold
    # start on a low-end runner.
    local = uno.getComponentContext()
    resolver = local.ServiceManager.createInstanceWithContext(
        "com.sun.star.bridge.UnoUrlResolver", local
    )
    full_url = f"uno:{connect}StarOffice.ComponentContext"
    ctx = None
    last_exc: Exception | None = None
    for _ in range(60):
        try:
            ctx = resolver.resolve(full_url)
            break
        except Exception as exc:  # noqa: BLE001 — pyuno raises bare Exception
            last_exc = exc
            time.sleep(0.25)
    if ctx is None:
        print(
            f"could not connect to soffice at {full_url}: {last_exc!r}",
            file=sys.stderr,
        )
        return 1

    desktop = ctx.ServiceManager.createInstanceWithContext(
        "com.sun.star.frame.Desktop", ctx
    )

    url = _to_file_url(target_path)
    try:
        # Explicit FilterName + ReadOnly=False bypasses LO's type-
        # detection registry, which isn't always initialized when
        # running with a fresh `-env:UserInstallation` profile.
        doc = desktop.loadComponentFromURL(
            url, "_blank", 0,
            (
                _prop("Hidden", True),
                _prop("ReadOnly", False),
                _prop("FilterName", "Calc Office Open XML"),
            ),
        )
        if doc is None:
            print(f"loadComponentFromURL returned None for {url}", file=sys.stderr)
            return 1
        try:
            doc.calculateAll()
            doc.storeToURL(
                url,
                (
                    _prop("FilterName", "Calc Office Open XML"),
                    _prop("Overwrite", True),
                ),
            )
        finally:
            doc.close(False)
    except Exception as exc:  # noqa: BLE001
        print(f"recalc/save failed: {exc!r}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
