Offline security tools for Debian 13 amd64 / matching Python minor version.

Download `install_offline.py`, `bundle_common.py`, the main `.tar.gz` and its `.sha256`
into the same directory. Transfer to Debian, then:

```sh
python3 install_offline.py --bundle security-tools-debian13-amd64.tar.gz
. "$HOME/security-tools/activate.sh"
"$HOME/security-tools/run-opencode.sh"
```

Optional ZAP/Java is a separate archive installed with the same installer.
See OFFLINE_INSTALL.md and resolved-versions.lock.json for exact versions/provenance.
Mandatory tests: clean Debian 13, UID 1000, network disabled, no system pip/sudo,
venv and pip-target installs, scanner fixtures, DB import, both browser launches,
repeat install and negative archive/platform/missing-library tests.

Real user-installed Security Audit Skill and full OpenCode/LLM session are NOT VERIFIED
in CI; only the explicitly labeled synthetic PATH/import contract is tested.
