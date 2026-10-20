#!/usr/bin/env python3
"""Isolated dispatch for tool entry points, also without venv/system pip."""
import json
import os
from pathlib import Path
import runpy
import sys


def main():
    root = Path(__file__).resolve().parent
    config = json.loads((root / "installation.json").read_text())
    tool = sys.argv.pop(1)
    # No empty entries (which would let the loader search an untrusted working directory),
    # and no inherited library paths from other tool environments.
    os.environ["LD_LIBRARY_PATH"] = str(root / "payload/runtime/lib")
    os.environ.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1",
                      HF_HUB_DISABLE_TELEMETRY="1", DO_NOT_TRACK="1",
                      SEMGREP_SEND_METRICS="off", SEMGREP_ENABLE_VERSION_CHECK="0",
                      TOKENIZERS_PARALLELISM="false", OMP_NUM_THREADS="2")
    os.environ["PATH"] = str(root / "bin") + os.pathsep + os.environ.get("PATH", "")
    env = config["environments"]["harness2" if tool.startswith("harness2") else "llamafirewall"]
    if os.environ.get("_AGENT_CONTROLS_CHILD") != str(root) + ":" + tool:
        os.environ["_AGENT_CONTROLS_CHILD"] = str(root) + ":" + tool
        flags = ["-I", "-S"] if env["target"] else ["-I"]
        os.execv(env["python"], [env["python"], *flags, str(__file__), tool, *sys.argv[1:]])
    if env["target"]:
        sys.path.insert(0, env["target"])
    # Do not expose this internal dispatch marker to tool subprocesses.
    os.environ.pop("_AGENT_CONTROLS_CHILD", None)
    if tool == "agent-firewall-scan":
        runpy.run_path(str(root / "firewall_scan.py"), run_name="__main__")
    elif tool == "agent-controls-python":
        if sys.argv[1:2] == ["-c"]:
            code = sys.argv[2]
            sys.argv = ["-c", *sys.argv[3:]]
            exec(compile(code, "<string>", "exec"), {"__name__": "__main__"})
        else:
            raise SystemExit("Use agent-controls-python -c '...' for isolated imports")
    else:
        from importlib.metadata import distribution
        package = "harness2" if tool.startswith("harness2") else "llamafirewall"
        if tool == "pysemgrep":
            package = "semgrep"
        entry = next(ep for ep in distribution(package).entry_points
                     if ep.group == "console_scripts" and ep.name == tool)
        sys.argv[0] = tool
        raise SystemExit(entry.load()())


if __name__ == "__main__":
    main()
