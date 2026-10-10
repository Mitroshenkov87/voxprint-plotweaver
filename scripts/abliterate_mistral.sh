#!/usr/bin/env bash
# Compatibility wrapper. The general command is scripts/abliterate.sh.
exec "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/abliterate.sh" mistral "$@"
