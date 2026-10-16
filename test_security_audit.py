#!/usr/bin/env python3
"""Read-only skill compatibility inspection. Never executes an unknown audit target."""
import argparse
import ast
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys


def inspect(skill, strict=False):
    skill = Path(skill).expanduser()
    if not (skill / "SKILL.md").is_file():
        print(json.dumps({"status": "NOT_VERIFIED", "reason": "Real security-audit skill unavailable",
                          "path": str(skill)}))
        return 2 if strict else 0
    imports = set()
    tools = set()
    recommendations = []
    for file in skill.rglob("*"):
        if file.suffix not in (".md", ".py", ".sh", ".json") or not file.is_file():
            continue
        text = file.read_text(errors="replace")
        tools.update(re.findall(r"\b(semgrep|checkov|gitleaks|grype|playwright|python3)\b", text))
        if file.suffix == ".py":
            tree = ast.parse(text, filename=str(file))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imports.update(n.name.split(".")[0] for n in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                    imports.add(node.module.split(".")[0])
        if re.search(r"(?:/usr/bin/python3|/usr/local/bin/python3|--config[ =]+(?:auto|p/|r/|https?://)|pip install|npx |docker run)", text):
            recommendations.append({"file": str(file.relative_to(skill)),
              "message": "Review absolute interpreter, registry config, or network installer; use activated python3 and local rules instead"})
    missing = []
    for name in sorted(imports - sys.stdlib_module_names):
        # No imports of skill modules (avoid side effects); find_spec only for top-level imports.
        result = subprocess.run([sys.executable, "-c", "import importlib.util,sys;sys.exit(importlib.util.find_spec(sys.argv[1]) is None)", name], capture_output=True)
        if result.returncode and not (skill / (name + ".py")).exists() and not (skill / name).is_dir():
            missing.append(name)
    absent = [tool for tool in tools if not shutil.which(tool)]
    report = {"status": "STATIC_COMPATIBLE" if not (missing or absent or recommendations) else "REVIEW_REQUIRED",
              "skill": str(skill), "missing_imports": missing, "missing_tools": absent,
              "recommendations": recommendations,
              "limits": "Read-only static check; not an end-to-end audit, LLM or OpenCode session test"}
    print(json.dumps(report, indent=2))
    return int(bool(missing or absent or recommendations))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--skill", default="~/.config/opencode/skills/security-audit")
    p.add_argument("--strict", action="store_true")
    a = p.parse_args()
    sys.exit(inspect(a.skill, a.strict))
