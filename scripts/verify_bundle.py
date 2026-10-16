#!/usr/bin/env python3
import argparse
from pathlib import Path
import sys
import tempfile
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bundle_common import safe_extract, verify_archive_checksum, verify_tree

p = argparse.ArgumentParser()
p.add_argument("archive")
a = p.parse_args()
verify_archive_checksum(a.archive)
with tempfile.TemporaryDirectory() as temp:
    safe_extract(a.archive, temp)
    manifest = verify_tree(temp)
    print("Verified", len(manifest["files"]), "files; Python", manifest["python_version"])
