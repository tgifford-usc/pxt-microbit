#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

RUNTIME_PATCH = """\

(function () {
  // Make bases absolute so new URL(relative, base) never throws in self-hosted builds
  var absBase = window.location.origin + (pxtConfig.relprefix || "/");

  // These are used as bases in various parts of PXT/MakeCode
  pxtConfig.cdnUrl = absBase;
  pxtConfig.pxtCdnUrl = absBase;
  pxtConfig.commitCdnUrl = absBase;
  pxtConfig.blobCdnUrl = absBase;

  // If your build/template ever leaves @cdnUrl@ tokens around, keep this consistent
  // (Your nginx /editor/blob proxy will handle the actual content.)
  // Nothing else needed here.
})();
"""

def patch_file(path: Path) -> None:
    text = path.read_text(encoding="utf-8")

    # idempotent: don't reinsert
    if "Make bases absolute so new URL" in text:
        print(f"OK: patch already present: {path}")
        return

    marker = "var pxtConfig = {"
    start = text.find(marker)
    if start == -1:
        raise SystemExit(f"ERROR: couldn't find '{marker}' in {path}")

    # Find the end of the config assignment in *your* format: newline then };
    end = text.find("\n};", start)
    if end == -1:
        # fallback: maybe it's "};" without a newline
        end = text.find("};", start)
        if end == -1:
            raise SystemExit(f"ERROR: couldn't find end of pxtConfig object ('}};') after marker in {path}")

    insert_at = end + len("\n};") if text[end:end+3] == "\n};" else end + 2

    patched = text[:insert_at] + "\n" + RUNTIME_PATCH + text[insert_at:]

    # Optional: also permanently replace @cdnUrl@ tokens in index.html
    patched = patched.replace("@cdnUrl@", "/editor")

    path.write_text(patched, encoding="utf-8")
    print(f"Patched: {path}")

def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("Usage: patch-staticpkg-index.py built/packaged/editor/index.html")

    path = Path(sys.argv[1])
    if not path.is_file():
        raise SystemExit(f"ERROR: not found: {path}")

    patch_file(path)

if __name__ == "__main__":
    main()
