import io
import json
from pathlib import Path
import platform
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

from bundle_common import safe_extract, verify_archive_checksum, verify_tree
from install_offline import check_platform


class InstallerSecurityTests(unittest.TestCase):
    def test_corrupted_archive(self):
        with tempfile.TemporaryDirectory() as tmp:
            file = Path(tmp) / "bad.tar.gz"
            file.write_bytes(b"corrupt")
            with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
                verify_archive_checksum(file, "0" * 64)

    def test_checksum_required(self):
        with tempfile.TemporaryDirectory() as tmp:
            file = Path(tmp) / "test.tar.gz"
            file.write_bytes(b"test")
            with self.assertRaisesRegex(ValueError, "Missing"):
                verify_archive_checksum(file)

    def test_traversal_and_links(self):
        for name, kind in (("../escaped", "file"), ("/absolute", "file"),
                           ("safe/../../escaped", "file"), ("link", "symlink"),
                           ("hard", "hardlink"), ("device", "device")):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp:
                archive = Path(tmp) / "bad.tar"
                with tarfile.open(archive, "w") as tar:
                    member = tarfile.TarInfo(name)
                    if kind == "symlink":
                        member.type = tarfile.SYMTYPE
                        member.linkname = "/etc"
                    elif kind == "hardlink":
                        member.type = tarfile.LNKTYPE
                        member.linkname = "/etc/passwd"
                    elif kind == "device":
                        member.type = tarfile.CHRTYPE
                    tar.addfile(member)
                with self.assertRaises(ValueError):
                    safe_extract(archive, Path(tmp) / "output")
                self.assertFalse((Path(tmp) / "escaped").exists())

    def test_wrong_architecture(self):
        with patch.object(platform, "machine", return_value="aarch64"):
            with self.assertRaisesRegex(ValueError, "x86_64"):
                check_platform({"architecture": "amd64", "python_version": "3.13"})

    def test_wrong_python(self):
        with patch.object(platform, "machine", return_value="x86_64"):
            with self.assertRaisesRegex(ValueError, "Python mismatch"):
                check_platform({"architecture": "amd64", "python_version": "0.0"})

    def test_inventory_tamper(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "MANIFEST.json").write_text('{"files":{}}')
            (root / "extra").write_text("unexpected")
            with self.assertRaisesRegex(ValueError, "inventory"):
                verify_tree(root)


if __name__ == "__main__":
    unittest.main()
