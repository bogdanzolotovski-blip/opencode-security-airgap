#!/usr/bin/env python3
"""Rootless offline installer. No networking and no third-party imports."""
import argparse
import json
import os
from pathlib import Path
import platform
import shlex
import shutil
import subprocess
import sys
import tempfile
import uuid

from bundle_common import safe_extract, verify_archive_checksum, verify_tree


def check_platform(manifest):
    if sys.platform != "linux" or platform.machine() not in ("x86_64", "amd64"):
        raise ValueError("This bundle requires Linux x86_64/amd64")
    if manifest["architecture"] != "amd64":
        raise ValueError("Bundle architecture is not amd64")
    actual = "%d.%d" % sys.version_info[:2]
    if actual != manifest["python_version"]:
        raise ValueError("Python mismatch: bundle=" + manifest["python_version"] +
                         ", interpreter=" + actual + "; use matching Python or rebuild")
    release = platform.freedesktop_os_release()
    if release.get("ID") != "debian" or release.get("VERSION_ID", "").split(".")[0] != "13":
        raise ValueError("Supported target: Debian 13 (Trixie)")


def pip_install(base, payload, tool, force_target=False):
    environment = base / "envs" / tool
    envpython = Path(sys.executable).resolve()
    target = None
    if not force_target:
        try:
            import venv
            venv.EnvBuilder(with_pip=False, symlinks=False).create(environment)
            envpython = environment / "bin/python3"
            subprocess.run([str(envpython), "-I", "-c", "import sys; assert sys.prefix != sys.base_prefix"],
                           check=True, capture_output=True)
        except (ImportError, OSError, subprocess.CalledProcessError):
            shutil.rmtree(environment, ignore_errors=True)
            target = environment / "site"
    else:
        target = environment / "site"
    if target is not None:
        target.mkdir(parents=True)
    pipwheel = next((payload / "bootstrap").glob("pip-*.whl"))
    code = "import sys,runpy; sys.path.insert(0,sys.argv.pop(1)); runpy.run_module('pip',run_name='__main__')"
    command = [str(envpython), "-I", "-c", code, str(pipwheel), "--isolated", "install",
               "--no-index", "--no-deps", "--no-compile", "--disable-pip-version-check",
               "--require-hashes", "--find-links", str(payload / "wheels" / tool),
               "-r", str(payload / "wheels" / tool / "requirements.txt")]
    if target is not None:
        command += ["--target", str(target), "--ignore-installed"]
    subprocess.run(command, check=True)
    return {"python": str(envpython), "target": str(target) if target else None}


def install(args):
    digest = verify_archive_checksum(args.bundle, args.sha256)
    prefix = Path(args.prefix).expanduser().resolve()
    prefix.mkdir(parents=True, exist_ok=True)
    # Directory lock avoids concurrent installers switching current unexpectedly.
    lock = prefix / ".install-lock"
    try:
        lock.mkdir()
    except FileExistsError:
        raise ValueError("Installer already running (or stale lock): " + str(lock))
    generation = prefix / "releases" / (digest[:16] + "-" + uuid.uuid4().hex[:8])
    generation.mkdir(parents=True)
    committed = False
    try:
        payload = generation / "payload"
        safe_extract(args.bundle, payload)
        manifest = verify_tree(payload)
        check_platform(manifest)
        if manifest.get("kind") == "zap":
            return install_zap(prefix, generation, payload, manifest)
        config = {"base_python": str(Path(sys.executable).resolve()), "environments": {}}
        for tool in ("semgrep", "checkov", "playwright"):
            config["environments"][tool] = pip_install(generation, payload, tool, args.force_target)
        (generation / "installation.json").write_text(json.dumps(config, indent=2))
        shutil.copy2(payload / "launcher.py", generation / "launcher.py")
        shutil.copy2(payload / "python_entry.py", generation / "python_entry.py")
        bindir = generation / "bin"
        bindir.mkdir()
        for tool in ("semgrep", "checkov", "gitleaks", "grype", "python3", "playwright", "zap"):
            wrapper = bindir / tool
            wrapper.write_text("#!/bin/sh\nexec " + shlex.quote(config["base_python"]) + " -I " +
                               shlex.quote(str(generation / "launcher.py")) + " " + tool + ' "$@"\n')
            wrapper.chmod(0o755)
        for script in ("verify_tools.py", "diagnose_browser.py", "test_security_audit.py"):
            shutil.copy2(payload / script, generation / script)
        subprocess.run([str(bindir / "python3"), str(generation / "verify_tools.py"),
                        "--root", str(generation)], check=True)
        skill_report = subprocess.run([str(bindir / "python3"), str(generation / "test_security_audit.py"),
                                       "--strict"], capture_output=True, text=True)
        (generation / "skill-compatibility-report.txt").write_text(skill_report.stdout + skill_report.stderr)
        if skill_report.returncode:
            print("SKILL: requires local review; see", generation / "skill-compatibility-report.txt")
        else:
            print("SKILL: static import/PATH compatibility passed; live OpenCode audit still requires validation")
        # Activate only after every mandatory installed-tool check passed.
        link = prefix / (".current-" + uuid.uuid4().hex)
        link.symlink_to(generation, target_is_directory=True)
        os.replace(link, prefix / "current")
        for name in ("bin", "verify_tools.py", "diagnose_browser.py", "test_security_audit.py"):
            path = prefix / name
            if not path.exists() and not path.is_symlink():
                path.symlink_to(Path("current") / name, target_is_directory=name == "bin")
        for name in ("activate.sh", "run-opencode.sh"):
            shutil.copy2(payload / name, prefix / name)
        (prefix / "run-opencode.sh").chmod(0o755)
        committed = True
        print("Installed successfully:", generation)
        print("Activate: export SECURITY_TOOLS_HOME=" + shlex.quote(str(prefix)) +
              "; . " + shlex.quote(str(prefix / "activate.sh")))
        print("Previous generations retained for rollback; no existing skill was modified.")
    finally:
        if not committed:
            shutil.rmtree(generation, ignore_errors=True)
        lock.rmdir()


def install_zap(prefix, generation, payload, manifest):
    # Optional archive is installed independently; main bundle is not required.
    java = payload / "java/bin/java"
    env = os.environ.copy()
    env["JAVA_HOME"] = str(payload / "java")
    subprocess.run([str(java), "-version"], env=env, check=True)
    zap = payload / "zap/zap.sh"
    env["PATH"] = str(java.parent) + os.pathsep + env.get("PATH", "")
    subprocess.run([str(zap), "-version"], env=env, check=True, timeout=120)
    # ZAP generation lives outside releases cleanup and is swapped atomically.
    final = prefix / "zap-releases" / generation.name
    final.parent.mkdir(exist_ok=True)
    generation.rename(final)
    link = prefix / (".zap-" + uuid.uuid4().hex)
    link.symlink_to(final / "payload", target_is_directory=True)
    os.replace(link, prefix / "zap-current")
    print("ZAP installed:", final)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", required=True)
    parser.add_argument("--sha256", help="Expected archive digest; otherwise require adjacent .sha256")
    parser.add_argument("--prefix", default="~/security-tools")
    parser.add_argument("--force-target", action="store_true", help="Test/use isolated pip --target fallback")
    args = parser.parse_args()
    try:
        install(args)
    except (ValueError, OSError, subprocess.SubprocessError, StopIteration) as error:
        print("INSTALL FAILED:", error, file=sys.stderr)
        print("Existing current installation was not switched. Check Python version, disk space and browser diagnostics.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
