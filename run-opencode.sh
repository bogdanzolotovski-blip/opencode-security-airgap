#!/bin/sh
set -eu
SECURITY_TOOLS_HOME="${SECURITY_TOOLS_HOME:-$HOME/security-tools}"
export SECURITY_TOOLS_HOME
. "$SECURITY_TOOLS_HOME/activate.sh"
exec opencode "$@"
