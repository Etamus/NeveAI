#!/bin/bash
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd -P)"
exec /bin/bash "$HERE/launch.sh" doctor "$@"
