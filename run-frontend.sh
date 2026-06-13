#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
export PATH="$SCRIPT_DIR/.local-node/bin:$PATH"

cd "$SCRIPT_DIR/frontend"
node ./node_modules/vite/bin/vite.js --host 0.0.0.0
