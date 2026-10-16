#!/usr/bin/env python3
"""Diagnose packaged Chromium and render a local page without an external URL."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


def diagnose(root=None, extra_binary=None):
    root = Path(root or os.environ.get("SECURITY_TOOLS_ROOT", Path(__file__).resolve().parent))
    payload = root / "payload"
    browserpath = Path(os.environ.get("PLAYWRIGHT_BROWSERS_PATH", payload / "browsers"))
    libraries = payload / "runtime/lib"
    env = os.environ.copy()
    env["LD_LIBRARY_PATH"] = str(libraries)
    candidates = [p for p in browserpath.rglob("*") if p.is_file() and p.name in
                  ("chrome", "headless_shell", "chrome-headless-shell")]
    if extra_binary:
        candidates.append(Path(extra_binary))
    if not candidates:
        raise RuntimeError("Chromium/headless shell missing at " + str(browserpath))
    missing = []
    if not shutil.which("ldd"):
        raise RuntimeError("ldd is missing; Debian libc-bin is required for diagnostics")
    for binary in candidates:
        result = subprocess.run(["ldd", str(binary)], env=env, capture_output=True, text=True)
        for line in (result.stdout + result.stderr).splitlines():
            if "not found" in line:
                missing.append(str(binary) + ": " + line.strip())
    if missing:
        raise RuntimeError("Missing .so dependencies:\n" + "\n".join(missing) +
                           "\nRebuild the Debian runtime pack; never replace system glibc.")
    from playwright.sync_api import sync_playwright
    with tempfile.TemporaryDirectory(prefix="airgap-browser-") as tmp:
        pagefile = Path(tmp) / "index.html"
        pagefile.write_text("<title>airgap-ok</title><h1 id='ok'>local-only</h1>")
        with sync_playwright() as pw:
            # chromium_sandbox=True preserves the browser sandbox. Root runs are prohibited.
            for label, options in (("headless-shell", {}), ("chromium", {"channel": "chromium"})):
                browser = pw.chromium.launch(headless=True, chromium_sandbox=True, **options)
                context = browser.new_context(offline=True)
                context.route("http://**/*", lambda route: route.abort())
                context.route("https://**/*", lambda route: route.abort())
                page = context.new_page()
                page.goto(pagefile.as_uri())
                assert page.title() == "airgap-ok"
                assert page.locator("#ok").inner_text() == "local-only"
                print(label + ": local render OK, browser=" + browser.version)
                browser.close()
    return {"browsers": [str(p) for p in candidates], "missing": []}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root")
    parser.add_argument("--extra-binary", help="Also diagnose a supplied ELF (negative tests)")
    args = parser.parse_args()
    try:
        diagnose(args.root, args.extra_binary)
    except Exception as error:
        print("BROWSER FAILED:", error, file=sys.stderr)
        print("If sandbox namespaces are denied by LXC/AppArmor, ask the Proxmox administrator for a suitable container policy or VM. No --no-sandbox workaround is enabled.", file=sys.stderr)
        sys.exit(1)
