#!/usr/bin/env python3
"""Debian 13 amd64 / CPython 3.13 offline, rootless, isolated installer."""
import argparse
import json
import os
from pathlib import Path
import platform
import shlex
import shutil
import subprocess
import sys
import uuid

from bundle_common import safe_extract, verify_archive_checksum, verify_tree

BASE = str(Path(getattr(sys, "_base_executable", sys.executable)).resolve())


def check_platform(manifest):
    if sys.platform != "linux" or platform.machine() not in ("x86_64", "amd64"):
        raise ValueError("Requires Linux amd64")
    if manifest["architecture"] != "amd64":
        raise ValueError("Wrong bundle architecture")
    import sysconfig
    if (platform.python_implementation() != "CPython" or
            sysconfig.get_config_var("Py_GIL_DISABLED") or
            manifest["python_version"] != "%d.%d" % sys.version_info[:2]):
        raise ValueError("Requires matching standard CPython " + manifest["python_version"])
    release = platform.freedesktop_os_release()
    if release.get("ID") != "debian" or release.get("VERSION_ID", "").split(".")[0] != "13":
        raise ValueError("Requires Debian 13 Trixie")
    if manifest.get("kind") != "agent-controls":
        raise ValueError("Not an agent-controls bundle")


def install_python(root, payload, tool, force_target):
    destination = root / "envs" / tool
    interpreter, target = BASE, None
    if not force_target:
        try:
            import venv
            venv.EnvBuilder(with_pip=False, symlinks=False).create(destination)
            interpreter = str(destination / "bin/python3")
            subprocess.run([interpreter, "-I", "-c", "import sys; assert sys.prefix != sys.base_prefix"],
                           check=True, capture_output=True)
        except (ImportError, OSError, subprocess.CalledProcessError):
            shutil.rmtree(destination, ignore_errors=True)
            interpreter = BASE
            target = destination / "site"
    else:
        target = destination / "site"
    if target is not None:
        target.mkdir(parents=True)
    pip = next((payload / "bootstrap").glob("pip-*.whl"))
    bootstrap = "import sys,runpy;sys.path.insert(0,sys.argv.pop(1));runpy.run_module('pip',run_name='__main__')"
    command = [interpreter, "-I", "-c", bootstrap, str(pip), "--isolated", "install", "--no-index",
               "--no-deps", "--no-compile", "--require-hashes", "--disable-pip-version-check",
               "--find-links", str(payload / "wheels" / tool),
               "-r", str(payload / "wheels" / tool / "requirements.txt")]
    if target is not None:
        command += ["--target", str(target), "--ignore-installed"]
    env = dict(os.environ, PIP_CONFIG_FILE=os.devnull, PIP_NO_INDEX="1")
    subprocess.run(command, check=True, env=env)
    return {"python": interpreter, "target": str(target) if target else None}


def install(args):
    digest = verify_archive_checksum(args.bundle, args.sha256)
    prefix = Path(args.prefix).expanduser().resolve()
    prefix.mkdir(parents=True, exist_ok=True)
    stable = prefix / "bin"
    if stable.is_symlink():
        if os.readlink(stable) != "current/bin":
            raise ValueError("Unexpected bin symlink: " + str(stable))
    elif stable.exists():
        raise ValueError("Refusing to replace unexpected bin path: " + str(stable))
    lock = prefix / ".install-lock"
    try:
        lock.mkdir()
    except FileExistsError:
        raise ValueError("Installer active or stale lock: " + str(lock))
    generation = prefix / "releases" / (digest[:16] + "-" + uuid.uuid4().hex[:8])
    committed = False
    try:
        generation.mkdir(parents=True)
        payload = generation / "payload"
        safe_extract(args.bundle, payload)
        manifest = verify_tree(payload)
        check_platform(manifest)
        envs = {tool: install_python(generation, payload, tool, args.force_target)
                for tool in ("harness2", "llamafirewall")}
        (generation / "installation.json").write_text(json.dumps({"environments": envs}, indent=2))
        for filename in ("launcher.py", "firewall_scan.py", "verify_agent_controls.py"):
            shutil.copy2(payload / "integration" / filename, generation / filename)
        bindir = generation / "bin"
        bindir.mkdir()
        for tool in ("harness2", "harness2-demo", "harness2-check", "harness2-report", "harness2-judge",
                     "llamafirewall", "agent-firewall-scan", "agent-controls-python", "pysemgrep"):
            wrapper = bindir / tool
            wrapper.write_text("#!/bin/sh\nexec " + shlex.quote(BASE) + " -I -S " +
                               shlex.quote(str(generation / "launcher.py")) + " " + tool + ' "$@"\n')
            wrapper.chmod(0o755)
        shutil.copy2(payload / "native/numbat", bindir / "numbat")
        # CodeShield invokes semgrep by name; route to official Python CE entry.
        (bindir / "semgrep").symlink_to("pysemgrep")
        for name in ("plugins", "sources", "licenses"):
            (generation / name).symlink_to(payload / name, target_is_directory=True)
        subprocess.run([BASE, "-I", str(generation / "verify_agent_controls.py"),
                        "--root", str(generation)], check=True)
        # Stable path is essential: generated numbat plugin embeds binary's absolute path.
        (prefix / ".current-next").symlink_to(generation, target_is_directory=True)
        os.replace(prefix / ".current-next", prefix / "current")
        committed = True
        if not stable.is_symlink():
            stable.symlink_to("current/bin", target_is_directory=True)
        (prefix / "activate.sh").write_text(
            'export PATH=' + shlex.quote(str(prefix / "bin")) + ':"$PATH"\n'
            'export AGENT_FIREWALL_BIN=' + shlex.quote(str(prefix / "bin/agent-firewall-scan")) + '\n'
            'export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 HF_HUB_DISABLE_TELEMETRY=1 DO_NOT_TRACK=1\n')
        print("Installed:", prefix)
        print("Activate: . " + shlex.quote(str(prefix / "activate.sh")))
        print("OpenCode configuration and skills were NOT changed. See AGENT_CONTROLS_RU.md.")
    finally:
        if not committed:
            shutil.rmtree(generation, ignore_errors=True)
        lock.rmdir()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", required=True)
    parser.add_argument("--sha256")
    parser.add_argument("--prefix", default="~/agent-controls")
    parser.add_argument("--force-target", action="store_true")
    args = parser.parse_args()
    try:
        install(args)
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        print("Installation failed:", error, file=sys.stderr)
        print("If a .so is missing, preserve its exact name; Debian 13 glibc/loader are never replaced.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
