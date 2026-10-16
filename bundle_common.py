"""Standard-library-only archive validation shared by builder and installer."""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import tarfile


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def safe_extract(archive, destination, max_bytes=16 * 1024**3):
    destination = Path(destination).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive, "r:*") as tar:
        members = tar.getmembers()
        total = 0
        seen = set()
        for member in members:
            name = member.name
            path = PurePosixPath(name)
            if (not name or path.is_absolute() or ".." in path.parts or
                    "\\" in name or ":" in name or name in seen):
                raise ValueError("Unsafe or duplicate archive path: " + name)
            seen.add(name)
            if not (member.isdir() or member.isfile()):
                raise ValueError("Links/devices/special files prohibited: " + name)
            target = (destination / name).resolve()
            if not target.is_relative_to(destination):
                raise ValueError("Archive path escapes destination: " + name)
            total += member.size
            if member.size < 0 or total > max_bytes or len(members) > 200000:
                raise ValueError("Archive resource limit exceeded")
        for member in members:
            target = destination / member.name
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                # Never preserve ownership, setuid/setgid, or executable writable bits.
                with tar.extractfile(member) as src, open(target, "xb") as dst:
                    import shutil
                    shutil.copyfileobj(src, dst)
                target.chmod(0o755 if member.mode & 0o111 else 0o644)


def verify_tree(root):
    root = Path(root)
    manifest = json.loads((root / "MANIFEST.json").read_text())
    expected = set(manifest["files"])
    actual = {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()}
    if actual != expected | {"MANIFEST.json"}:
        raise ValueError("Bundle file inventory differs from manifest")
    for name, digest in manifest["files"].items():
        path = (root / name).resolve()
        if not path.is_relative_to(root.resolve()) or sha256(path) != digest:
            raise ValueError("SHA-256 mismatch: " + name)
    return manifest


def verify_archive_checksum(archive, expected=None):
    archive = Path(archive)
    if expected is None:
        sidecar = Path(str(archive) + ".sha256")
        if not sidecar.is_file():
            raise ValueError("Missing " + str(sidecar) + "; copy it with the archive")
        expected = sidecar.read_text().split()[0]
    if len(expected) != 64 or any(c not in "0123456789abcdefABCDEF" for c in expected):
        raise ValueError("Invalid SHA-256 digest")
    actual = sha256(archive)
    if actual.lower() != expected.lower():
        raise ValueError("Archive SHA-256 mismatch; installation cancelled before extraction")
    return actual
