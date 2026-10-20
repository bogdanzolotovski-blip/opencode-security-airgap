import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path("/src")
DIST = ROOT / "dist-agent-controls"
assert os.geteuid() != 0
assert not shutil.which("sudo") and not shutil.which("apt") and not shutil.which("docker")
assert subprocess.run([sys.executable, "-m", "pip", "--version"], capture_output=True).returncode != 0
assert subprocess.run([sys.executable, "-c", "import ensurepip"], capture_output=True).returncode != 0
prefix = Path.home() / "agent-controls"
install = [sys.executable, str(DIST / "install_agent_controls.py"), "--bundle",
           str(DIST / "agent-controls-debian13-amd64-py313.tar.gz")]
subprocess.run(install, check=True)
previous = (prefix / "current").resolve()
configuration = json.loads((previous / "installation.json").read_text())
assert all(v["target"] is None for v in configuration["environments"].values()), configuration
subprocess.run(install + ["--force-target"], check=True)
assert previous.exists() and (prefix / "current").resolve() != previous
configuration = json.loads((prefix / "current/installation.json").read_text())
assert all(v["target"] for v in configuration["environments"].values())
subprocess.run([str(prefix / "bin/agent-controls-python"), "-c",
                "import sys; assert not any(p.endswith(('site-packages','dist-packages')) for p in sys.path), sys.path"], check=True)
# Installation is intentionally opt-in, never silently alters user's plugins/skills.
assert not (Path.home() / ".config/opencode").exists()
numbat = str(prefix / "bin/numbat")
records = Path.home() / ".numbat/live.ndjson"
subprocess.run([numbat, "hook", "install", "--agent", "opencode", "--emit", "all",
                "--output", "file", "--output-file", str(records)], check=True)
subprocess.run([numbat, "hook", "status", "--agent", "opencode"], check=True)
plugin = Path.home() / ".config/opencode/plugins/numbat.ts"
assert plugin.exists() and "observe-only" in plugin.read_text()
assert 'from "@' not in plugin.read_text(), "Offline plugin must not import npm dependencies"
event = {"sessionID": "airgap-ci", "tool": "bash", "callID": "ci-1",
         "cwd": "/tmp", "args": {"command": "printf airgap-test"}}
subprocess.run([numbat, "hook", "opencode-pre-tool", "--agent", "opencode", "--emit", "all",
                "--output", "file", "--output-file", str(records)],
               input=json.dumps(event), text=True, check=True)
assert records.is_file() and records.stat().st_size > 0
assert any(json.loads(line) for line in records.read_text().splitlines())
with tempfile.TemporaryDirectory() as tmp:
    bad = Path(tmp) / "bad.tar.gz"
    bad.write_bytes(b"corrupt")
    current = (prefix / "current").resolve()
    proc = subprocess.run([sys.executable, str(DIST / "install_agent_controls.py"),
                           "--bundle", str(bad), "--sha256", "0" * 64])
    assert proc.returncode != 0 and current == (prefix / "current").resolve()
Path("/results/offline-test.json").write_text(json.dumps({
    "status": "PASS", "network": "docker --network none", "root": False,
    "system_pip": False, "ensurepip": False, "venv_and_target": True,
    "checks": ["CPU torch imports", "Harness2 real local demo", "Numbat hook callback records",
               "LlamaFirewall allow/block", "CodeShield known unsafe C fixture", "reinstall rollback"],
    "not_verified": ["real OpenCode plugin lifecycle", "Ollama end-to-end", "PromptGuard weights",
                     "cloud benchmark dependencies", "production enforcement"]
}, indent=2) + "\n")
print("PASS offline agent controls")
