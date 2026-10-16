"""Python command adapter for a pip --target environment (executed with -I)."""
import json
import os
from pathlib import Path
import runpy
import sys

root = Path(__file__).resolve().parent
cfg = json.loads((root / "installation.json").read_text())
target = cfg["environments"]["playwright"]["target"]
if target:
    sys.path.insert(0, target)
sys.executable = str(root / "bin/python3")
args = sys.argv[1:]
while args and args[0] in ("-u", "-B", "-s", "-E", "-I"):
    flag = args.pop(0)
    if flag == "-B":
        sys.dont_write_bytecode = True
    if flag == "-u":
        for stream in (sys.stdout, sys.stderr):
            if hasattr(stream, "reconfigure"):
                stream.reconfigure(write_through=True)
if not args:
    import code
    code.interact()
elif args[0] in ("--version", "-V"):
    print(sys.version)
elif args[0] == "-c":
    sys.argv = ["-c"] + args[2:]
    sys.path.insert(0, os.getcwd())
    exec(compile(args[1], "<string>", "exec"), {"__name__": "__main__"})
elif args[0] == "-m":
    sys.argv = args[1:]
    sys.path.insert(0, os.getcwd())
    runpy.run_module(args[1], run_name="__main__", alter_sys=True)
elif args[0] == "-":
    sys.argv = args
    sys.path.insert(0, os.getcwd())
    exec(compile(sys.stdin.read(), "<stdin>", "exec"), {"__name__": "__main__"})
else:
    if not args or args[0].startswith("-"):
        raise SystemExit("Unsupported Python switch in target fallback; use a Python with venv")
    sys.argv = args
    sys.path.insert(0, str(Path(args[0]).resolve().parent))
    runpy.run_path(args[0], run_name="__main__")
