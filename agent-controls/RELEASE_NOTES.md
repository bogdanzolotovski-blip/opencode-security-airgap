# Offline agent controls for Debian 13 amd64 / CPython 3.13

Rootless independent add-on: Google Research Harness2 core/source/offline demo,
official Perplexity Numbat v0.3.0, Meta LlamaFirewall 1.0.3 + CodeShield and CPU PyTorch.

Download the tar.gz and its .sha256, install_agent_controls.py and bundle_common.py
into one directory. On Debian: `python3 install_agent_controls.py --bundle agent-controls-debian13-amd64-py313.tar.gz`.
See AGENT_CONTROLS_RU.md for opt-in OpenCode monitoring and filtering configuration.

Release gate: clean Debian, unprivileged/no network, no pip/ensurepip, both venv
and isolated target installation; scanners, real harness demo, numbat callback,
negative installer tests and plugin subprocess/failure contracts.

Limitations: Numbat's OpenCode plugin is observe-only. The optional authored
LlamaFirewall plugin checks tool argument text only, defaults to monitor and is
not an OS sandbox. PromptGuard weights/gated models, AlignmentCheck and full
cloud benchmark environments are NOT included. Real target OpenCode/Ollama
integration is NOT VERIFIED by CI. No existing skill/config is overwritten.
