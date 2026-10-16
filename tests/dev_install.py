"""Developer-only fast feedback using an already checksummed CI payload.

Not a release gate: code is overlaid after manifest verification. Official CI always
tests the final immutable archive with install_offline.py instead.
"""
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
sys.path.insert(0, "/src")
from bundle_common import safe_extract, verify_archive_checksum, verify_tree
from install_offline import pip_install

root = Path.home() / "debug-tools"
payload = root / "payload"
if not payload.exists():
    verify_archive_checksum("/artifacts/security-tools-debian13-amd64.tar.gz")
    safe_extract("/artifacts/security-tools-debian13-amd64.tar.gz", payload)
    verify_tree(payload)
for name in ("launcher.py", "python_entry.py", "verify_tools.py", "diagnose_browser.py", "test_security_audit.py"):
    shutil.copy2(Path("/src") / name, root / name)
if not (payload / "native/git").exists() and Path("/usr/bin/git").exists():
    shutil.copy2("/usr/bin/git", payload / "native/git")
if not (root / "installation.json").exists():
    config = {"base_python": sys.executable, "environments": {}}
    for tool in ("semgrep", "checkov", "playwright"):
        config["environments"][tool] = pip_install(root, payload, tool)
    (root / "installation.json").write_text(json.dumps(config))
(root / "bin").mkdir(exist_ok=True)
for tool in ("semgrep", "checkov", "gitleaks", "grype", "git", "python3", "playwright"):
    path = root / "bin" / tool
    path.write_text("#!/bin/sh\nexec " + shlex.quote(sys.executable) + " -I " + shlex.quote(str(root / "launcher.py")) + " " + tool + ' "$@"\n')
    path.chmod(0o755)
subprocess.run([str(root / "bin/python3"), str(root / "verify_tools.py"), "--root", str(root)], check=True)
