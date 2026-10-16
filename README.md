# OpenCode Security Airgap — Debian 13 amd64

Rootless offline toolkit for an existing OpenCode installation. No target-side
apt, Docker, npm, sudo, system pip or network bootstrap. Python 3.13 by default.

Download a **successful Release**, its installer, `bundle_common.py`, archive and
adjacent `.sha256` file. Transfer all four to Debian and run:

```sh
python3 install_offline.py --bundle security-tools-debian13-amd64.tar.gz
. "$HOME/security-tools/activate.sh"
"$HOME/security-tools/run-opencode.sh"
```

See [OFFLINE_INSTALL.md](OFFLINE_INSTALL.md) for installation, checks and limitations.

## Components

Semgrep CE with authored local OWASP/CWE-tagged starter rules; Gitleaks with
official embedded rules; Checkov offline IaC checks; Grype with a version-compatible
Anchore database; Python Playwright with its exact Chromium and headless-shell
revisions; optional ZAP + Temurin JRE 21 with the distribution's included addons.

The small authored Semgrep ruleset is **not full OWASP coverage**. Additional vetted
local rules can be passed via `semgrep --config /path/to/rules`. Checkov does not
download Terraform modules and skips frameworks requiring other runtimes/cloud
services. A Debian Git binary and its runtime libraries support local history scans;
the wrapper permits only the file transport, not remote Git downloads.

## Build

GitHub Actions → Build and verify offline security tools → Run workflow.
Inputs: Python version, amd64 architecture, optional ZAP. amd64 is the only validated
architecture; unsupported architectures are rejected instead of mislabeled.
Alternate Python inputs use the matching official CPython/Trixie test image with
pip removed; only 3.13 uses Debian's distribution Python in the minimal test image.
If a pinned dependency has no compatible wheel, that build fails instead of building
an unreviewed sdist or publishing an incompatible artifact.
Top-level versions are pinned in `versions.lock.json`. Every build records the exact
transitive wheel versions/hashes, Debian runtime versions, browser revisions, DB
metadata and source URLs in `resolved-versions.lock.json` and the archive manifest.
Transitive dependencies are freshly resolved then fully locked per artifact; builds
are not claimed bit-for-bit reproducible across days. Official image digest is recorded.

Every asset must be <2 GiB; main and ZAP archives are independent. Large assets fail
the build rather than upload truncated data. Git history contains source only.
Artifacts remain downloadable even when a test or Release permission fails; a failed
run's artifact is **not a verified Release**.

## Validation and trust

Mandatory tests run in Debian 13 as UID 1000 with `--network none`, no system pip and
no sudo. Both fresh venv and isolated `pip --target` modes are exercised. Browser
sandbox remains enabled. Docker test harness allows namespace syscalls to test it;
the ephemeral Ubuntu CI host also permits unprivileged user namespaces in AppArmor.
an LXC host may need administrator-provided user-namespace/AppArmor support.

Installer validates the archive's external SHA-256 before extraction and every
payload file against its manifest, rejects links/path traversal/devices and checks
platform/Python. Obtain installer and checksum through a trusted Release: hashes
detect corruption, not a malicious replacement of both code and hashes.

Downloads use official PyPI, GitHub release publishers, Playwright CDNs, Anchore and
Adoptium. PyPI hashes and published release checksums/digests are verified. The
Playwright browser installer supplies the revision from the exact wheel; browser
files are hashed after download. An independent upstream browser checksum/signature
verification is not claimed. Debian libraries come from signed Debian repositories;
glibc and the ELF loader are never bundled. License files remain in wheels/browser/
Java/ZAP trees; native-tool and Debian library notices are included separately.

Offline settings prevent ordinary update/telemetry downloads, not arbitrary network
traffic from user code, a scan target, or an explicitly requested network subcommand.
Enforce air-gap at the OS/network layer. Grype DB becomes stale: date/source are
recorded, age rejection is disabled to permit offline use, never to imply freshness.

## Existing Security Audit Skill

`~/.config/opencode/skills/security-audit/` is never modified. The activated `python3`
has Playwright, requests, YAML and BeautifulSoup available. The scanners have separate
dependency environments. Absolute `/usr/bin/python3` calls bypass the adapter.

```sh
python3 "$HOME/security-tools/test_security_audit.py" --strict
```

This performs read-only inspection of real imports/calls. Unknown scripts are not
executed against production targets. CI uses a labeled synthetic compatibility
contract; actual installed skill and end-to-end OpenCode/LLM integration remain
**NOT VERIFIED** until tested on the target. Missing dependencies or registry calls
are reported as recommendations, never silently patched.
