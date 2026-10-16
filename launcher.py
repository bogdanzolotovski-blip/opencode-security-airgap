"""Installed tool dispatcher; no network bootstrap or dependency downloads."""
import importlib.metadata
import json
import os
from pathlib import Path
import runpy
import sys

root = Path(__file__).resolve().parent
payload = root / "payload"
cfg = json.loads((root / "installation.json").read_text())
tool, *args = sys.argv[1:]
env = os.environ.copy()
env["PATH"] = str(root / "bin") + os.pathsep + env.get("PATH", "")
for key in ("PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV", "SEMGREP_APP_TOKEN", "BC_API_KEY", "PRISMA_API_URL"):
    env.pop(key, None)
env.update({
    "SEMGREP_SEND_METRICS": "off", "SEMGREP_ENABLE_VERSION_CHECK": "0",
    "OTEL_SDK_DISABLED": "true", "DO_NOT_TRACK": "1",
    "SEMGREP_SETTINGS_FILE": str(root / "semgrep-settings.yml"),
    "CHECKOV_SKIP_DOWNLOAD": "true", "DOWNLOAD_EXTERNAL_MODULES": "false",
    "BC_SKIP_MAPPING": "true", "BC_SKIP_PLATFORM_INTEGRATION": "true",
    "AWS_EC2_METADATA_DISABLED": "true",
    "GRYPE_CHECK_FOR_APP_UPDATE": "false", "GRYPE_DB_AUTO_UPDATE": "false",
    "GRYPE_DB_VALIDATE_AGE": "false", "GRYPE_DB_REQUIRE_UPDATE_CHECK": "false",
    "GRYPE_DB_CACHE_DIR": str(root / "grype-db"),
    "GRYPE_CONFIG": str(payload / "configs/grype.yaml"),
    "GITLEAKS_CONFIG": str(payload / "configs/gitleaks.toml"),
    "PLAYWRIGHT_BROWSERS_PATH": str(payload / "browsers"),
    "PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD": "1", "PIP_NO_INDEX": "1",
    "PIP_DISABLE_PIP_VERSION_CHECK": "1", "PYTHONNOUSERSITE": "1",
    "SECURITY_TOOLS_ROOT": str(root),
})
if tool in ("semgrep", "checkov"):
    env["LD_LIBRARY_PATH"] = str(payload / "runtime/lib")
if tool in ("gitleaks", "grype", "git"):
    env["LD_LIBRARY_PATH"] = str(payload / "runtime/lib")
    env["GIT_ALLOW_PROTOCOL"] = "file"
    if tool == "grype" and len(args) > 1 and args[0] == "db":
        if args[1] in ("update", "check", "list"):
            raise SystemExit("Offline Grype: DB network operations disabled; transfer a new bundle")
        if args[1] == "import" and (len(args) < 3 or not Path(args[2]).is_file()):
            raise SystemExit("Offline Grype: db import requires a local archive")
    if tool == "grype" and args and args[0] not in ("version", "--version", "help", "--help", "db", "config", "completion"):
        if not any(a.startswith(("dir:", "sbom:", "file:")) or Path(a).exists() for a in args if not a.startswith("-")):
            raise SystemExit("Offline Grype: use dir:/path or sbom:/path; remote image lookup is disabled by policy")
    os.execve(str(payload / "native" / tool), [tool] + args, env)
if tool == "zap":
    prefix = root.parent.parent
    zaproot = prefix / "zap-current"
    if not zaproot.exists():
        raise SystemExit("Optional ZAP archive not installed")
    env["JAVA_HOME"] = str(zaproot / "java")
    env["PATH"] = str(zaproot / "java/bin") + os.pathsep + env.get("PATH", "")
    os.execve(str(zaproot / "zap/zap.sh"), ["zap.sh", "-dir", str(prefix / "zap-state"),
              "-config", "autoupdate.checkOnStart=false", "-config", "autoupdate.downloadNewRelease=false",
              "-config", "autoupdate.downloadNewAddons=false"] + args, env)
group = "playwright" if tool == "python3" else tool
spec = cfg["environments"][group]
if group == "playwright":
    env["LD_LIBRARY_PATH"] = str(payload / "runtime/lib")
    env["FONTCONFIG_FILE"] = str(root / "fontconfig.xml")
if tool == "python3":
    os.execve(spec["python"], [spec["python"], "-I", str(root / "python_entry.py")] + args, env)
if os.environ.get("AIRGAP_TOOL_CHILD") != group:
    env["AIRGAP_TOOL_CHILD"] = group
    os.execve(spec["python"], [spec["python"], "-I", str(__file__), tool] + args, env)
os.environ.clear()
os.environ.update(env)
if spec["target"]:
    sys.path.insert(0, spec["target"])
if tool == "semgrep":
    # Registry aliases and URLs would trigger network access: reject them.
    for i, arg in enumerate(args):
        value = args[i + 1] if arg in ("--config", "-c") and i + 1 < len(args) else None
        if arg.startswith("--config="):
            value = arg.split("=", 1)[1]
        if value is not None and not Path(value).exists():
            raise SystemExit("Offline Semgrep requires a local --config path")
    if not any(a in ("--version", "--help", "-h") for a in args):
        if not any(a in ("--config", "-c") or a.startswith("--config=") for a in args):
            if args and args[0] == "scan":
                args = ["scan", "--config", str(payload / "rules")] + args[1:]
            else:
                args = ["--config", str(payload / "rules")] + args
        args += ["--metrics=off", "--disable-version-check"]
elif tool == "checkov" and not any(a in ("--version", "--help", "-h") for a in args):
    args += ["--config-file", str(payload / "configs/checkov.yaml"),
             "--skip-download", "--download-external-modules", "false"]
elif tool == "playwright" and args and args[0] in ("install", "install-deps", "uninstall"):
    raise SystemExit("Browser installation is managed by the offline bundle")
sys.argv = [tool] + args
if tool == "playwright":
    runpy.run_module("playwright", run_name="__main__")
elif tool == "checkov":
    import warnings
    def deny_checkov_network(event, arguments):
        if event == "socket.getaddrinfo" or (event == "socket.connect" and isinstance(arguments[1], tuple)):
            raise RuntimeError("Checkov network access disabled by offline policy")
    sys.addaudithook(deny_checkov_network)
    from checkov.main import Checkov
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=SyntaxWarning)
        sys.exit(Checkov().run())
else:
    distname = "semgrep" if tool == "semgrep" else "checkov"
    entry = next(e for e in importlib.metadata.distribution(distname).entry_points
                 if e.group == "console_scripts" and e.name == tool)
    sys.exit(entry.load()())
