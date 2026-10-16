# Source this file: . "$HOME/security-tools/activate.sh"
export SECURITY_TOOLS_HOME="${SECURITY_TOOLS_HOME:-$HOME/security-tools}"
export PATH="$SECURITY_TOOLS_HOME/bin:$PATH"
# Tool-specific environment is injected by wrappers, not globally into OpenCode.
