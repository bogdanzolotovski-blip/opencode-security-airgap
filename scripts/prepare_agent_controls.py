#!/usr/bin/env python3
"""Online CI builder; target installation never runs this file."""
from datetime import datetime, timezone
from email.parser import BytesParser
import hashlib
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import urllib.parse
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from bundle_common import sha256, safe_extract
from prepare_bundle import api, download, ORIGINS


def torch_url(version):
    class Links(HTMLParser):
        urls = []
        def handle_starttag(self, tag, attrs):
            if tag == "a":
                self.urls.extend(v for k, v in attrs if k == "href")
    parser = Links()
    index = "https://download.pytorch.org/whl/cpu/torch/"
    with urllib.request.urlopen(index, timeout=120) as response:
        parser.feed(response.read().decode())
    matches = []
    for url in parser.urls:
        name = urllib.parse.unquote(urllib.parse.urlparse(url).path.rsplit("/", 1)[-1])
        if (name.startswith("torch-" + version + "-cp313-cp313-") and
                name.endswith("x86_64.whl") and "manylinux" in name):
            matches.append(urllib.parse.urljoin(index, url))
    if len(matches) != 1:
        raise ValueError("Expected one official CPU torch cp313 wheel, got " + repr(matches))
    url = matches[0]
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in ("download.pytorch.org", "download-r2.pytorch.org"):
        raise ValueError("Unexpected torch publisher")
    digest = urllib.parse.parse_qs(parsed.fragment).get("sha256", [None])[0]
    if not digest or len(digest) != 64:
        raise ValueError("Official torch index must supply sha256")
    return url, digest


def lock_wheels(directory, special=None):
    locked, packages = [], []
    for wheel in sorted(directory.glob("*.whl")):
        with zipfile.ZipFile(wheel) as z:
            metadata = BytesParser().parsebytes(z.read(next(n for n in z.namelist() if n.endswith(".dist-info/METADATA"))))
        name, version = metadata["Name"], metadata["Version"]
        digest = sha256(wheel)
        if special and name.lower() in special:
            source, expected = special[name.lower()]
        else:
            data = api("https://pypi.org/pypi/" + name + "/" + version + "/json")
            upstream = next(f for f in data["urls"] if f["filename"] == wheel.name)
            source, expected = upstream["url"], upstream["digests"]["sha256"]
        if digest != expected:
            raise ValueError("Wheel publisher checksum mismatch: " + wheel.name)
        ORIGINS.append({"url": source, "file": wheel.name, "sha256": digest})
        packages.append({"name": name, "version": version, "wheel": wheel.name,
                         "sha256": digest, "source": source,
                         "license": metadata.get("License-Expression") or metadata.get("License")})
        locked.append(f"{name}=={version} --hash=sha256:{digest}")
    (directory / "requirements.txt").write_text("\n".join(locked) + "\n")
    return packages


def main():
    if sys.platform != "linux" or sys.version_info[:2] != (3, 13):
        raise SystemExit("Build with official python:3.13-trixie, Linux amd64")
    lock = json.loads((ROOT / "agent-controls/versions.lock.json").read_text())
    work = ROOT / "build/agent-controls"
    if work.exists():
        shutil.rmtree(work)
    payload = work / "payload"
    payload.mkdir(parents=True)
    dist = ROOT / "dist-agent-controls"
    dist.mkdir(exist_ok=True)
    # Build tools run online only, on CI. No target-side compiler or installer downloads.
    subprocess.run([sys.executable, "-m", "pip", "install", "--index-url", "https://pypi.org/simple",
                    "setuptools==" + lock["setuptools"], "wheel==" + lock["wheel"]], check=True)
    harness_url = "https://codeload.github.com/google-research/harness2/tar.gz/" + lock["harness2_commit"]
    harness_archive = work / "harness2.tar.gz"
    download(harness_url, harness_archive, lock.get("harness2_source_sha256"))
    sources = payload / "sources"
    sources.mkdir()
    safe_extract(harness_archive, work / "harness-unpack")
    harness_source = next((work / "harness-unpack").iterdir())
    shutil.copytree(harness_source, sources / "harness2")
    harness_wheels = payload / "wheels/harness2"
    harness_wheels.mkdir(parents=True)
    subprocess.run([sys.executable, "-m", "pip", "wheel", "--no-deps", "--no-build-isolation",
                    "--wheel-dir", str(harness_wheels), str(harness_source)], check=True)
    built_wheel = next(harness_wheels.glob("*.whl"))
    packages = {"harness2": lock_wheels(harness_wheels, {"harness2": (harness_url, sha256(built_wheel))})}
    packages["harness2"][0]["provenance"] = "Wheel built locally from pinned official Git commit/archive; not a PyPI wheel"
    lf = payload / "wheels/llamafirewall"
    lf.mkdir(parents=True)
    cpu_url, cpu_digest = torch_url(lock["torch"])
    requirements = ["llamafirewall==" + lock["llamafirewall"], "codeshield==" + lock["codeshield"],
                    "transformers==" + lock["transformers"], "semgrep==" + lock["semgrep"], cpu_url]
    subprocess.run([sys.executable, "-m", "pip", "--isolated", "download", "--only-binary=:all:",
                    "--index-url", "https://pypi.org/simple", "--dest", str(lf), *requirements], check=True)
    packages["llamafirewall"] = lock_wheels(lf, {"torch": (cpu_url, cpu_digest)})
    boot = payload / "bootstrap"
    boot.mkdir()
    subprocess.run([sys.executable, "-m", "pip", "--isolated", "download", "--only-binary=:all:",
                    "--no-deps", "--index-url", "https://pypi.org/simple", "--dest", str(boot),
                    "pip==" + lock["pip"]], check=True)
    packages["bootstrap"] = lock_wheels(boot)
    release = api("https://api.github.com/repos/perplexityai/numbat/releases/tags/v" + lock["numbat"])
    assetname = f"numbat_{lock['numbat']}_linux_amd64.tar.gz"
    asset = next(a for a in release["assets"] if a["name"] == assetname)
    checksum = next(a for a in release["assets"] if a["name"] == "checksums.txt")
    download(checksum["browser_download_url"], work / "numbat-checksums.txt")
    expected = next(line.split()[0] for line in (work / "numbat-checksums.txt").read_text().splitlines()
                    if line.split()[-1].lstrip("*") == assetname)
    if expected != lock["numbat_sha256"] or asset.get("digest") != "sha256:" + expected:
        raise ValueError("Pinned numbat checksum changed")
    archive = work / "numbat.tar.gz"
    download(asset["browser_download_url"], archive, expected)
    safe_extract(archive, work / "numbat-unpack")
    native = payload / "native"
    native.mkdir()
    binary = next(p for p in (work / "numbat-unpack").rglob("numbat") if p.is_file())
    shutil.copy2(binary, native / "numbat")
    (native / "numbat").chmod(0o755)
    licenses = payload / "licenses"
    licenses.mkdir()
    shutil.copytree(work / "numbat-unpack", licenses / "numbat", ignore=shutil.ignore_patterns("numbat"))
    shutil.copy2(work / "numbat-checksums.txt", licenses / "numbat-checksums.txt")
    for doc in ("README.md", "docs/agent-coverage.md", "docs/deployment.md", "docs/enforcement.md", "docs/cli.md", "LICENSE"):
        download(f"https://raw.githubusercontent.com/perplexityai/numbat/v{lock['numbat']}/" + doc,
                 sources / "numbat" / doc)
    integration = payload / "integration"
    integration.mkdir()
    for filename in ("launcher.py", "firewall_scan.py", "verify_agent_controls.py"):
        shutil.copy2(ROOT / "agent-controls" / filename, integration / filename)
    shutil.copytree(ROOT / "agent-controls/plugins", payload / "plugins")
    # Local plugin loader treats exports as factories: do not export test helpers.
    assert "export function checkText" not in (payload / "plugins/airgap-firewall.js").read_text()
    manifest = {"schema": 1, "kind": "agent-controls", "architecture": "amd64", "python_version": "3.13",
                "created_utc": datetime.now(timezone.utc).isoformat(), "versions": lock,
                "packages": packages, "sources": ORIGINS,
                "limitations": ["PromptGuard weights NOT included; gated Meta access required",
                                "AlignmentCheck/cloud benchmark dependencies NOT included",
                                "Numbat OpenCode integration is observe-only",
                                "Harness2 core + deterministic offline demo; full benchmarks NOT provisioned",
                                "Real target OpenCode/Ollama integration NOT verified in CI"],
                "files": {p.relative_to(payload).as_posix(): sha256(p) for p in sorted(payload.rglob("*")) if p.is_file()}}
    (payload / "MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n")
    bundle = dist / "agent-controls-debian13-amd64-py313.tar.gz"
    with tarfile.open(bundle, "w:gz", compresslevel=1, dereference=True) as tar:
        for path in sorted(payload.iterdir()):
            tar.add(path, arcname=path.name)
    if bundle.stat().st_size >= 2 * 1024**3:
        raise ValueError("Release asset exceeds GitHub limit")
    (dist / (bundle.name + ".sha256")).write_text(sha256(bundle) + "  " + bundle.name + "\n")
    (dist / "agent-controls-resolved.json").write_text(json.dumps(manifest, indent=2) + "\n")
    for source in (ROOT / "agent-controls/install_agent_controls.py", ROOT / "bundle_common.py",
                   ROOT / "AGENT_CONTROLS_RU.md"):
        shutil.copy2(source, dist / source.name)
    print("Built:", bundle, bundle.stat().st_size)


if __name__ == "__main__":
    main()
