#!/usr/bin/env python3
"""Verify immutable legacy artifacts directly from their published Git tag."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "tests/vectors/legacy-v1.3.0-sha256.json"


def main() -> int:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    tag = manifest["tag"]
    failed = False
    for path, expected in manifest["files"].items():
        try:
            content = subprocess.run(
                ["git", "show", f"{tag}:{path}"],
                cwd=ROOT,
                check=True,
                capture_output=True,
            ).stdout
        except subprocess.CalledProcessError as error:
            failed = True
            print(f"FAIL {tag}:{path}: {error.stderr.decode().strip()}")
            continue
        actual = hashlib.sha256(content).hexdigest()
        if actual != expected:
            failed = True
            print(f"FAIL {tag}:{path}: SHA-256 {actual}, expected {expected}")
        else:
            print(f"OK   {tag}:{path} {actual}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
