#!/usr/bin/env python3
"""Resolve a database compatible with this exact Grype binary, verify and import."""
import json
import os
from pathlib import Path
import subprocess
import urllib.request
from urllib.parse import urljoin


def prepare(binary, destination, download):
    env = os.environ.copy()
    env["GRYPE_DB_CACHE_DIR"] = str(destination / "validation-cache")
    env["GRYPE_CHECK_FOR_APP_UPDATE"] = "false"
    listing = subprocess.check_output([str(binary), "db", "list", "-o", "json"], env=env, text=True)
    (destination / "grype-db-listing.json").write_text(listing)
    parsed = json.loads(listing)
    entries = parsed.get("available", parsed.get("databases", [])) if isinstance(parsed, dict) else parsed
    if not entries:
        raise RuntimeError("No compatible Grype DB in listing: " + listing[:1000])
    item = sorted(entries, key=lambda x: x.get("built", ""), reverse=True)[0]
    major = item.get("schemaVersion", "v6").split(".")[0]
    url = item.get("url") or urljoin("https://grype.anchore.io/databases/" + major + "/", item["path"])
    if not url.startswith("https://"):
        raise RuntimeError("Refusing non-HTTPS Grype database")
    archive = destination / ("grype-db.tar.zst" if url.endswith(".zst") else "grype-db.tar.gz")
    checksum = item.get("checksum", "").removeprefix("sha256:")
    if len(checksum) != 64:
        raise RuntimeError("Grype DB listing has no SHA-256")
    download(url, archive, checksum)
    subprocess.run([str(binary), "db", "import", str(archive)], env=env, check=True)
    status = subprocess.check_output([str(binary), "db", "status", "-o", "json"], env=env, text=True)
    (destination / "grype-db-status.json").write_text(status)
    import shutil
    shutil.rmtree(destination / "validation-cache")
    return {"source": url, "checksum": checksum, "listing_entry": item,
            "status": json.loads(status)}
