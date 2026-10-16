#!/usr/bin/env python3
"""Build only inside the pinned official Python/Debian Trixie container."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
import zipfile
from email.parser import BytesParser

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from bundle_common import sha256
from prepare_grype_db import prepare as prepare_db

ORIGINS = []


def api(url):
    request = urllib.request.Request(url, headers={"User-Agent": "opencode-security-airgap-builder/1"})
    with urllib.request.urlopen(request, timeout=120) as response:
        return json.load(response)


def download(url, target, expected=None):
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(url, headers={"User-Agent": "opencode-security-airgap-builder/1"})
    with urllib.request.urlopen(request, timeout=300) as response, open(target, "wb") as output:
        shutil.copyfileobj(response, output)
    digest = sha256(target)
    if expected and digest.lower() != expected.lower():
        raise RuntimeError("Upstream checksum mismatch: " + url)
    ORIGINS.append({"url": url, "file": target.name, "sha256": digest,
                    "upstream_checksum_verified": bool(expected)})
    return digest


def release(repo, version):
    return api("https://api.github.com/repos/" + repo + "/releases/tags/v" + version)


def native(repo, name, version, archname, payload, work):
    data = release(repo, version)
    assetname = f"{name}_{version}_linux_{archname}.tar.gz"
    asset = next(a for a in data["assets"] if a["name"] == assetname)
    checksum_asset = next(a for a in data["assets"] if a["name"].endswith("_checksums.txt"))
    checksums = work / (name + "-checksums.txt")
    download(checksum_asset["browser_download_url"], checksums)
    expected = next(line.split()[0] for line in checksums.read_text().splitlines()
                    if line.split()[-1].lstrip("*") == assetname)
    archive = work / assetname
    download(asset["browser_download_url"], archive, expected)
    with tarfile.open(archive) as tar:
        for member in tar.getmembers():
            if not member.isfile():
                continue
            leaf = Path(member.name).name
            if leaf == name:
                dest = payload / "native" / name
            elif re.search(r"license|notice|copying", leaf, re.I):
                dest = payload / "licenses" / name / leaf
            else:
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            with tar.extractfile(member) as src, open(dest, "wb") as dst:
                shutil.copyfileobj(src, dst)
            if leaf == name:
                dest.chmod(0o755)
    shutil.copy2(checksums, payload / "licenses" / (name + "-checksums.txt"))


def wheels(payload, tool, requirements):
    directory = payload / "wheels" / tool
    directory.mkdir(parents=True)
    subprocess.run([sys.executable, "-m", "pip", "--isolated", "download", "--only-binary=:all:",
                    "--index-url", "https://pypi.org/simple", "--dest", str(directory)] + requirements, check=True)
    locked = []
    packages = []
    for wheel in sorted(directory.glob("*.whl")):
        with zipfile.ZipFile(wheel) as zipf:
            metadata = BytesParser().parsebytes(zipf.read(next(n for n in zipf.namelist() if n.endswith(".dist-info/METADATA"))))
        name, version = metadata["Name"], metadata["Version"]
        data = api("https://pypi.org/pypi/" + name + "/" + version + "/json")
        upstream = next(f for f in data["urls"] if f["filename"] == wheel.name)
        digest = sha256(wheel)
        if digest != upstream["digests"]["sha256"]:
            raise RuntimeError("PyPI digest mismatch: " + wheel.name)
        ORIGINS.append({"file": wheel.name, "url": upstream["url"], "sha256": digest,
                        "upstream_checksum_verified": True})
        locked.append(f"{name}=={version} --hash=sha256:{digest}")
        packages.append({"name": name, "version": version, "wheel": wheel.name,
                         "license": metadata.get("License-Expression") or metadata.get("License")})
    (directory / "requirements.txt").write_text("\n".join(locked) + "\n")
    return packages


def normalized_copy(source, dest):
    """Dereference upstream links; final bundle never needs archive links."""
    shutil.copytree(source, dest, symlinks=False, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))


def runtime_libraries(payload):
    libdir = payload / "runtime/lib"
    libdir.mkdir(parents=True)
    # Debian glibc is always provided by target OS. Never bundle its ABI/loader.
    glibc = re.compile(r"^(ld-linux.*|libc\.so.*|libm\.so.*|libpthread\.so.*|librt\.so.*|libdl\.so.*|libresolv\.so.*|libutil\.so.*|libanl\.so.*)$")
    pending = []
    for path in (payload / "browsers").rglob("*"):
        if path.is_file() and (path.stat().st_mode & 0o111 or ".so" in path.name):
            with open(path, "rb") as stream:
                if stream.read(4) == b"\x7fELF":
                    pending.append(path)
    pending += list(Path("/usr/lib/x86_64-linux-gnu").glob("libudev.so.1"))
    pending += list(Path("/usr/lib/x86_64-linux-gnu").glob("libgmp.so.10"))
    pending += list((payload / "native").glob("git"))
    copied = set()
    owners = set()
    while pending:
        binary = pending.pop()
        result = subprocess.run(["ldd", str(binary)], capture_output=True, text=True)
        if "not found" in result.stdout:
            raise RuntimeError("Builder has missing browser dependencies: " + result.stdout)
        deps = re.findall(r"=> (/\S+)", result.stdout)
        if str(binary).startswith("/usr/lib/"):
            deps.append(str(binary))
        for name in deps:
            path = Path(name)
            if path.name in copied or glibc.match(path.name) or str(path).startswith(str(payload)):
                continue
            copied.add(path.name)
            shutil.copyfile(path, libdir / path.name)
            pending.append(path)
            owner = subprocess.run(["dpkg-query", "-S", str(path)], capture_output=True, text=True)
            if owner.returncode:
                owner = subprocess.run(["dpkg-query", "-S", str(path.resolve())], capture_output=True, text=True)
            if owner.returncode == 0:
                owners.add(owner.stdout.split(": ")[0])
    records = []
    for owner in sorted(owners):
        package = owner.split(":")[0]
        copyright_file = Path("/usr/share/doc") / package / "copyright"
        dest = payload / "licenses/debian" / package
        dest.mkdir(parents=True, exist_ok=True)
        if copyright_file.exists():
            shutil.copy2(copyright_file, dest / "copyright")
        records.append(subprocess.check_output(["dpkg-query", "-W", "-f=${Package}=${Version}\n", owner], text=True).strip())
    (payload / "runtime/debian-packages.txt").write_text("\n".join(records) + "\n")
    return records


def archive(payload, output, metadata):
    metadata["files"] = {p.relative_to(payload).as_posix(): sha256(p)
                         for p in sorted(payload.rglob("*")) if p.is_file() and p.name != "MANIFEST.json"}
    (payload / "MANIFEST.json").write_text(json.dumps(metadata, indent=2) + "\n")
    with tarfile.open(output, "w:gz", dereference=True) as tar:
        for path in sorted(payload.rglob("*")):
            if path.is_file():
                tar.add(path, arcname=path.relative_to(payload).as_posix(), recursive=False)
    if output.stat().st_size >= 2 * 1024**3:
        output.unlink()
        raise RuntimeError("Asset exceeds 2 GiB; publish a smaller independent component bundle")
    Path(str(output) + ".sha256").write_text(sha256(output) + "  " + output.name + "\n")


def zap_bundle(lock, args, dist, work):
    payload = work / "zap-payload"
    payload.mkdir()
    data = release("zaproxy/zaproxy", lock["zap"])
    asset = next(a for a in data["assets"] if a["name"] == "ZAP_" + lock["zap"] + "_Linux.tar.gz")
    expected = asset.get("digest", "").removeprefix("sha256:")
    if len(expected) != 64:
        raise RuntimeError("GitHub ZAP asset has no published SHA-256 digest")
    zaparchive = work / asset["name"]
    download(asset["browser_download_url"], zaparchive, expected)
    # Trusted/checksummed upstream tar extracted only into disposable build tree.
    zaptemp = work / "zap-extract"
    zaptemp.mkdir()
    subprocess.run(["tar", "-xzf", str(zaparchive), "-C", str(zaptemp), "--no-same-owner"], check=True)
    normalized_copy(next(zaptemp.iterdir()), payload / "zap")
    java = api("https://api.adoptium.net/v3/assets/latest/" + str(lock["java_major"]) +
               "/hotspot?architecture=x64&image_type=jre&os=linux&vendor=eclipse")[0]
    pkg = java["binary"]["package"]
    jarchive = work / "java.tar.gz"
    download(pkg["link"], jarchive, pkg["checksum"])
    jtemp = work / "java-extract"
    jtemp.mkdir()
    subprocess.run(["tar", "-xzf", str(jarchive), "-C", str(jtemp), "--no-same-owner"], check=True)
    normalized_copy(next(jtemp.iterdir()), payload / "java")
    addons = sorted(p.name for p in (payload / "zap/plugin").glob("*.zap"))
    if not addons:
        raise RuntimeError("ZAP distribution does not contain offline addons")
    metadata = {"kind": "zap", "python_version": args.python_version, "architecture": args.architecture,
                "built_at": datetime.now(timezone.utc).isoformat(), "zap": lock["zap"],
                "java": java["release_name"], "addons": addons, "origins": ORIGINS.copy()}
    archive(payload, dist / "security-zap-debian13-amd64.tar.gz", metadata)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--python-version", default="3.13")
    parser.add_argument("--architecture", default="amd64", choices=["amd64"])
    parser.add_argument("--include-zap", action="store_true")
    args = parser.parse_args()
    if "%d.%d" % sys.version_info[:2] != args.python_version:
        raise RuntimeError("Builder Python must match python_version input")
    lock = json.loads((ROOT / "versions.lock.json").read_text())
    dist = ROOT / "dist"
    dist.mkdir(exist_ok=True)
    work = ROOT / "build"
    if work.exists():
        shutil.rmtree(work)
    work.mkdir()
    payload = work / "payload"
    payload.mkdir()
    for name in ("rules", "configs"):
        normalized_copy(ROOT / name, payload / name)
    for name in ("launcher.py", "python_entry.py", "verify_tools.py", "diagnose_browser.py", "test_security_audit.py",
                 "activate.sh", "run-opencode.sh", "LICENSE", "versions.lock.json"):
        shutil.copy2(ROOT / name, payload / name)
    (payload / "bootstrap").mkdir()
    subprocess.run([sys.executable, "-m", "pip", "download", "--index-url", "https://pypi.org/simple",
                    "--only-binary=:all:", "--no-deps", "-d", str(payload / "bootstrap"), "pip==" + lock["pip"]], check=True)
    bootstrap = next((payload / "bootstrap").glob("*.whl"))
    pipinfo = api("https://pypi.org/pypi/pip/" + lock["pip"] + "/json")
    pipasset = next(a for a in pipinfo["urls"] if a["filename"] == bootstrap.name)
    assert sha256(bootstrap) == pipasset["digests"]["sha256"]
    ORIGINS.append({"file": bootstrap.name, "url": pipasset["url"], "sha256": sha256(bootstrap), "upstream_checksum_verified": True})
    resolved = {}
    for tool in ("semgrep", "checkov", "playwright"):
        reqs = [tool + "==" + lock[tool]]
        if tool == "playwright":
            reqs += ["requests==2.32.5", "PyYAML==6.0.3", "beautifulsoup4==4.14.3"]
        resolved[tool] = wheels(payload, tool, reqs)
    native("gitleaks/gitleaks", "gitleaks", lock["gitleaks"], "x64", payload, work)
    native("anchore/grype", "grype", lock["grype"], "amd64", payload, work)
    git = Path("/usr/bin/git")
    if not git.exists():
        raise RuntimeError("Builder must include Debian git for offline history scans")
    shutil.copy2(git, payload / "native/git")
    (payload / "licenses/git").mkdir()
    shutil.copy2("/usr/share/doc/git/copyright", payload / "licenses/git/copyright")
    gitversion = subprocess.check_output(["dpkg-query", "-W", "-f=${Version}", "git"], text=True)
    ORIGINS.append({"file": "native/git", "source": "Debian signed apt repository / official Python Trixie image",
                    "version": gitversion, "sha256": sha256(git)})
    (payload / "data").mkdir()
    database = prepare_db(payload / "native/grype", payload / "data", download)
    # Install browser driver in a disposable build venv, never transfer this venv.
    envdir = work / "browser-env"
    subprocess.run([sys.executable, "-m", "venv", str(envdir)], check=True)
    python = envdir / "bin/python"
    subprocess.run([str(python), "-m", "pip", "install", "--no-index", "--find-links", str(payload / "wheels/playwright"),
                    "playwright==" + lock["playwright"]], check=True)
    env = os.environ.copy()
    env["PLAYWRIGHT_BROWSERS_PATH"] = str(payload / "browsers")
    subprocess.run([str(python), "-m", "playwright", "install", "--with-deps", "chromium"], env=env, check=True)
    for path in (payload / "browsers").rglob("*"):
        if path.is_symlink():
            data = path.read_bytes()
            mode = path.stat().st_mode
            path.unlink()
            path.write_bytes(data)
            path.chmod(mode & 0o777)
    registry = envdir / "lib" / ("python" + args.python_version) / "site-packages/playwright/driver/package/browsers.json"
    browserinfo = json.loads(registry.read_text())
    shutil.copy2(registry, payload / "browsers-version.json")
    packages = runtime_libraries(payload)
    fontdir = Path("/usr/share/fonts/truetype/dejavu")
    if fontdir.exists():
        normalized_copy(fontdir, payload / "runtime/fonts")
        notice = Path("/usr/share/doc/fonts-dejavu-core/copyright")
        if notice.exists():
            shutil.copy2(notice, payload / "licenses/dejavu-fonts-copyright")
    metadata = {"kind": "main", "architecture": args.architecture, "python_version": args.python_version,
                "debian": "13", "built_at": datetime.now(timezone.utc).isoformat(),
                "versions": lock, "resolved_wheels": resolved, "browser_versions": browserinfo,
                "runtime_debian_packages": packages, "grype_database": database, "origins": ORIGINS,
                "real_skill_integration": "NOT_VERIFIED: supply real skill to test_security_audit.py",
                "rules": "Authored MIT starter rules, OWASP/CWE tags; not complete OWASP coverage",
                "browser_provenance": "Exact Playwright wheel + browsers.json, official Playwright installer HTTPS CDN; no independent upstream browser checksum published"}
    output = dist / "security-tools-debian13-amd64.tar.gz"
    archive(payload, output, metadata)
    (dist / "resolved-versions.lock.json").write_text(json.dumps(metadata, indent=2))
    for file in ("install_offline.py", "bundle_common.py", "OFFLINE_INSTALL.md"):
        shutil.copy2(ROOT / file, dist / file)
    if args.include_zap:
        zap_bundle(lock, args, dist, work)
    print("Bundle ready:", output, output.stat().st_size)


if __name__ == "__main__":
    main()
