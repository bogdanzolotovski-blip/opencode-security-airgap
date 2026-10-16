"""Executed as unprivileged user inside --network none Debian 13."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path("/src")
BUNDLE = ROOT / "dist/security-tools-debian13-amd64.tar.gz"
PREFIX = Path.home() / "security-tools"
assert os.geteuid() != 0, "Must test without root"
assert subprocess.run([sys.executable, "-m", "pip", "--version"], capture_output=True).returncode != 0, "System pip must be absent"
assert shutil.which("sudo") is None, "sudo must be absent"
subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "/src/tests", "-p", "test_installer.py", "-v"], cwd=ROOT, check=True)
command = [sys.executable, str(ROOT / "install_offline.py"), "--bundle", str(BUNDLE)]
subprocess.run(command, check=True)
before = (PREFIX / "current").resolve()
# Reinstall through forced isolated --target fallback, retaining prior generation.
subprocess.run(command + ["--force-target"], check=True)
assert before.exists()
assert (PREFIX / "current").resolve() != before
env = os.environ.copy()
env["PATH"] = str(PREFIX / "bin") + os.pathsep + env["PATH"]
python = PREFIX / "bin/python3"
subprocess.run([str(python), "-c", "import playwright.sync_api,requests,yaml,bs4; print('Python audit imports OK')"], check=True, env=env)
# This contract fixture tests PATH and subprocess wiring, not the user's real skill.
with tempfile.TemporaryDirectory() as tmp:
    skill = Path(tmp) / "security-audit"
    skill.mkdir()
    (skill / "SKILL.md").write_text("Synthetic contract only: python3 semgrep checkov gitleaks grype playwright\n")
    (skill / "dast.py").write_text("from playwright.sync_api import sync_playwright\nimport requests\n")
    subprocess.run([str(python), str(PREFIX / "test_security_audit.py"), "--skill", str(skill), "--strict"], check=True, env=env)
    subprocess.run([str(python), str(PREFIX / "test_security_audit.py")], check=True, env=env)
# A dynamically linked ELF requires a deliberately removed private library.
missing = subprocess.run([str(python), str(PREFIX / "diagnose_browser.py"), "--extra-binary", "/opt/missing-so-fixture"], capture_output=True, text=True, env=env)
assert missing.returncode != 0 and "libairgapmissing.so" in missing.stderr, missing.stderr
# Corrupt reinstall must preserve working current.
with tempfile.TemporaryDirectory() as tmp:
    bad = Path(tmp) / "bad.tar.gz"
    bad.write_bytes(b"corrupt")
    current = (PREFIX / "current").resolve()
    result = subprocess.run([sys.executable, str(ROOT / "install_offline.py"), "--bundle", str(bad), "--sha256", "0" * 64])
    assert result.returncode != 0
    assert current == (PREFIX / "current").resolve()
zap = ROOT / "dist/security-zap-debian13-amd64.tar.gz"
if zap.exists():
    subprocess.run([sys.executable, str(ROOT / "install_offline.py"), "--bundle", str(zap)], check=True)
    subprocess.run([str(PREFIX / "bin/zap"), "-version"], check=True, env=env, timeout=120)
result = {"status": "PASS", "network": "docker --network none", "root": False,
          "system_pip": False, "venv_and_target": True,
          "real_skill": "NOT_VERIFIED; synthetic contract tested only"}
print(json.dumps(result))
Path("/results/offline-test.json").write_text(json.dumps(result, indent=2))
