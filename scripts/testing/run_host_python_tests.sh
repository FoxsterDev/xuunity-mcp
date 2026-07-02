#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SOURCE_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

cd "$SOURCE_ROOT"
python3 scripts/testing/check_release_version_consistency.py
python3 scripts/testing/check_release_docs_freshness.py
python3 -m unittest discover -s tests -v
