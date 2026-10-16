#!/usr/bin/env python3
"""Write external checksums only after mandatory smoke tests succeeded."""
import hashlib
import json
from pathlib import Path
import shutil

root = Path(__file__).resolve().parents[1]
evidence = json.loads((root / "test-results/offline-test.json").read_text())
if evidence["status"] != "PASS":
    raise SystemExit("Mandatory offline tests did not pass")
dist = root / "dist"
lines = []
for file in sorted(dist.iterdir()):
    if file.is_file() and file.name != "SHA256SUMS":
        if file.stat().st_size >= 2 * 1024**3:
            raise SystemExit("Release asset exceeds 2 GiB: " + file.name)
        digest = hashlib.file_digest(file.open("rb"), "sha256").hexdigest()
        lines.append(digest + "  " + file.name)
(dist / "SHA256SUMS").write_text("\n".join(lines) + "\n")
