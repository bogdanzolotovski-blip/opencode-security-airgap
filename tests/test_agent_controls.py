import importlib.util
import io
import json
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from bundle_common import safe_extract, verify_archive_checksum, verify_tree
spec = importlib.util.spec_from_file_location("install_controls", ROOT / "agent-controls/install_agent_controls.py")
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


class AgentControlsTests(unittest.TestCase):
    def test_checksum_before_unpack(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp) / "bad.tar.gz"
            archive.write_bytes(b"broken")
            with self.assertRaisesRegex(ValueError, "before extraction"):
                verify_archive_checksum(archive, "0" * 64)

    def test_paths_and_links(self):
        for name, kind in [("../escape", tarfile.REGTYPE), ("/absolute", tarfile.REGTYPE),
                           ("link", tarfile.SYMTYPE), ("hard", tarfile.LNKTYPE), ("dev", tarfile.CHRTYPE)]:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp:
                archive = Path(tmp) / "bad.tar"
                with tarfile.open(archive, "w") as tar:
                    member = tarfile.TarInfo(name)
                    member.type = kind
                    member.linkname = "../escape"
                    tar.addfile(member, io.BytesIO(b""))
                with self.assertRaises(ValueError):
                    safe_extract(archive, Path(tmp) / "destination")

    def test_platform(self):
        manifest = {"architecture": "amd64", "python_version": "3.13", "kind": "agent-controls"}
        with patch.object(installer.sys, "platform", "linux"), patch.object(installer.platform, "machine", return_value="x86_64"):
            with self.assertRaisesRegex(ValueError, "architecture"):
                installer.check_platform(dict(manifest, architecture="arm64"))
            with self.assertRaisesRegex(ValueError, "CPython"):
                installer.check_platform(dict(manifest, python_version="9.99"))

    def test_manifest_tamper(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "MANIFEST.json").write_text(json.dumps({"files": {"x": "0" * 64}}))
            (root / "x").write_text("tampered")
            with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
                verify_tree(root)

    def test_never_bundle_gated_models_or_cloud_defaults(self):
        source = (ROOT / "agent-controls/firewall_scan.py").read_text()
        self.assertNotIn("ScannerType.PROMPT_GUARD", source)
        self.assertNotIn("ScannerType.AGENT_ALIGNMENT", source)
        plugin = (ROOT / "agent-controls/plugins/airgap-firewall.js").read_text()
        self.assertIn('process.env.AGENT_FIREWALL_MODE || "monitor"', plugin)
        self.assertNotIn("export function checkText", plugin)


if __name__ == "__main__":
    unittest.main()
