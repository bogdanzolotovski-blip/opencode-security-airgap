#!/usr/bin/env python3
"""Mandatory offline smoke tests using only synthetic public fixtures."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


def run(command, expected=(0,), env=None, timeout=240):
    result = subprocess.run([str(x) for x in command], env=env, capture_output=True,
                            text=True, timeout=timeout)
    if result.returncode not in expected:
        raise RuntimeError("Command failed: " + str(command) + "\n" + result.stdout[-4000:] + result.stderr[-4000:])
    return result


def verify(root, browser=True):
    root = Path(root).resolve()
    binaries = root / "bin"
    locked = json.loads((root / "payload/versions.lock.json").read_text())
    for tool, flag in (("semgrep", "--version"), ("checkov", "--version"),
                       ("gitleaks", "version"), ("grype", "version"), ("playwright", "--version")):
        result = run([binaries / tool, flag])
        assert locked[tool] in result.stdout + result.stderr, "Wrong version: " + tool
        print(tool + ": " + (result.stdout or result.stderr).strip()[:300])
    with tempfile.TemporaryDirectory(prefix="airgap-fixtures-") as temp:
        fixture = Path(temp)
        (fixture / "bad.py").write_text("eval(input())\n")
        result = run([binaries / "semgrep", "scan", "--json", "--no-git-ignore", fixture])
        report = json.loads(result.stdout)
        assert any("eval-input" in f["check_id"] for f in report["results"]), "Local Semgrep rule did not match"
        (fixture / "main.tf").write_text('resource "aws_s3_bucket" "bad" {\n bucket = "airgap-public-test"\n}\n')
        result = run([binaries / "checkov", "-f", fixture / "main.tf", "--framework", "terraform", "-o", "json"], expected=(0, 1))
        assert 'CKV' in result.stdout, "Checkov did not run local checks"
        # Gitleaks must find a synthetic fixture; this is not a real credential.
        (fixture / "synthetic.txt").write_text('api_key = "' + 'AKIA' + 'Q7R9U2E5B6N8K4M3' + '"\n')
        result = run([binaries / "gitleaks", "dir", str(fixture), "--no-banner",
                      "--report-format", "json", "--report-path", str(fixture / "secrets.json")], expected=(0, 1))
        assert json.loads((fixture / "secrets.json").read_text()), "Gitleaks did not find synthetic secret"
        run([binaries / "git", "init", str(fixture)])
        run([binaries / "git", "-C", fixture, "add", "synthetic.txt"])
        run([binaries / "git", "-C", fixture, "-c", "user.name=Airgap Test", "-c", "user.email=test@example.invalid",
             "commit", "-m", "synthetic fixture"])
        env = os.environ.copy()
        env["PATH"] = str(binaries) + os.pathsep + env.get("PATH", "")
        run([binaries / "gitleaks", "git", str(fixture), "--no-banner", "--report-format", "json",
             "--report-path", str(fixture / "history.json")], expected=(1,), env=env)
        assert json.loads((fixture / "history.json").read_text()), "Git-history scan did not find fixture"
        dbarchive = next((root / "payload/data").glob("grype-db.tar.*"))
        run([binaries / "grype", "db", "import", dbarchive], timeout=300)
        run([binaries / "grype", "db", "status"])
        # Minimal CycloneDX SBOM exercises real DB lookup without package registries.
        sbom = fixture / "bom.json"
        sbom.write_text(json.dumps({"bomFormat": "CycloneDX", "specVersion": "1.5", "version": 1,
            "components": [{"type": "library", "name": "requests", "version": "2.19.1",
                            "purl": "pkg:pypi/requests@2.19.1"}]}))
        result = run([binaries / "grype", "sbom:" + str(sbom), "-o", "json"])
        assert "matches" in json.loads(result.stdout), "Grype did not scan SBOM"
    if browser:
        run([binaries / "python3", root / "diagnose_browser.py", "--root", root], timeout=180)
        print("Chromium + headless shell: OK (sandbox enabled)")
    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=os.environ.get("SECURITY_TOOLS_ROOT", "~/security-tools/current"))
    parser.add_argument("--skip-browser", action="store_true", help="Diagnostic only; not a release gate")
    args = parser.parse_args()
    try:
        verify(Path(args.root).expanduser(), not args.skip_browser)
    except Exception as error:
        print("VERIFY FAILED:", error, file=sys.stderr)
        sys.exit(1)
