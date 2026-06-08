#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

if [[ "${PLAYWRIGHT_SKIP_NPM_CI:-0}" != "1" && ( ! -d node_modules/@playwright/test || package-lock.json -nt node_modules/.package-lock.json ) ]]; then
  npm ci
fi

if [[ "${PLAYWRIGHT_SKIP_BROWSER_INSTALL:-0}" != "1" ]]; then
  npx playwright install chromium
fi

npm run test:site:ui
