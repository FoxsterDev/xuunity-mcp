#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
OPS_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
WRAPPER="$OPS_ROOT/xuunity_light_unity_mcp.sh"

PROJECT_ROOT=""
OPEN_EDITOR="true"
RESTORE_EDITOR_STATE="true"
RETAIN_FIXTURES="false"
TMP_DIR=""
GENERATED_ROOT=""
GENERATED_DIR=""

ASSEMBLY_NAME="XUUnity.LightMcp.Generated.EditModeTargetedFilterColdDiscovery.Tests"
FULL_TEST_NAME="XUUnity.LightMcp.Generated.EditModeTargetedFilterColdDiscovery.XUUnityLightMcpGeneratedEditModeTargetedFilterColdDiscoveryTests.FullyQualifiedTargetIsDiscoveredAfterRefresh"

usage() {
  cat <<'EOF'
Usage:
  run_editmode_targeted_filter_cold_discovery_suite.sh \
    --project-root /path/to/UnityProject \
    [--no-open-editor] \
    [--no-restore-editor-state] \
    [--retain-fixtures]
EOF
}

fail_usage() {
  echo "$1" >&2
  usage >&2
  exit 1
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --project-root)
      shift
      [[ $# -gt 0 ]] || fail_usage "--project-root requires a value"
      PROJECT_ROOT="$1"
      ;;
    --no-open-editor)
      OPEN_EDITOR="false"
      ;;
    --no-restore-editor-state)
      RESTORE_EDITOR_STATE="false"
      ;;
    --retain-fixtures)
      RETAIN_FIXTURES="true"
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      fail_usage "Unknown argument: $1"
      ;;
  esac
  shift
done

[[ -n "$PROJECT_ROOT" ]] || fail_usage "missing required argument: --project-root"
TMP_DIR="$(mktemp -d)"
GENERATED_ROOT="$PROJECT_ROOT/Assets/XUUnityLightMcpGenerated"
GENERATED_DIR="$GENERATED_ROOT/EditModeTargetedFilterColdDiscovery"

cleanup() {
  if [[ "$RETAIN_FIXTURES" != "true" && -n "$GENERATED_DIR" && -d "$GENERATED_DIR" ]]; then
    rm -rf "$GENERATED_DIR"
    rm -f "$GENERATED_DIR.meta"
    if [[ -d "$GENERATED_ROOT" && -z "$(find "$GENERATED_ROOT" -mindepth 1 -maxdepth 1 -print -quit)" ]]; then
      rmdir "$GENERATED_ROOT" || true
      rm -f "$GENERATED_ROOT.meta"
    fi
    "$WRAPPER" request-project-refresh \
      --project-root "$PROJECT_ROOT" \
      --timeout-ms 180000 >/dev/null 2>&1 || true
  fi
  if [[ "$RESTORE_EDITOR_STATE" == "true" ]]; then
    "$WRAPPER" restore-editor-state \
      --project-root "$PROJECT_ROOT" \
      --timeout-ms 60000 >/dev/null 2>&1 || true
  fi
  rm -rf "$TMP_DIR"
}
trap cleanup EXIT

fail_step() {
  local step_name="$1"
  local output_path="$TMP_DIR/${step_name}.json"
  echo "[fail] $step_name" >&2
  if [[ -f "$output_path" ]]; then
    cat "$output_path" >&2
  fi
  exit 1
}

run_step() {
  local step_name="$1"
  shift
  if ! "$@" >"$TMP_DIR/${step_name}.json" 2>&1; then
    fail_step "$step_name"
  fi
}

if [[ -e "$GENERATED_DIR" ]]; then
  fail_usage "generated fixture path already exists: $GENERATED_DIR"
fi

ensure_ready_cmd=(
  "$WRAPPER" ensure-ready
  --project-root "$PROJECT_ROOT"
  --timeout-ms 300000
)
if [[ "$OPEN_EDITOR" == "true" ]]; then
  ensure_ready_cmd+=(--open-editor)
fi
run_step "ensure_ready" "${ensure_ready_cmd[@]}"

mkdir -p "$GENERATED_DIR"
cat >"$GENERATED_DIR/XUUnityLightMcpGeneratedEditModeTargetedFilterColdDiscovery.Tests.asmdef" <<'EOF'
{
  "name": "XUUnity.LightMcp.Generated.EditModeTargetedFilterColdDiscovery.Tests",
  "rootNamespace": "XUUnity.LightMcp.Generated.EditModeTargetedFilterColdDiscovery",
  "references": [],
  "includePlatforms": ["Editor"],
  "excludePlatforms": [],
  "allowUnsafeCode": false,
  "overrideReferences": false,
  "precompiledReferences": [],
  "optionalUnityReferences": ["TestAssemblies"],
  "autoReferenced": false,
  "defineConstraints": [],
  "versionDefines": [],
  "noEngineReferences": false
}
EOF

cat >"$GENERATED_DIR/XUUnityLightMcpGeneratedEditModeTargetedFilterColdDiscoveryTests.cs" <<'EOF'
using NUnit.Framework;

namespace XUUnity.LightMcp.Generated.EditModeTargetedFilterColdDiscovery
{
    public sealed class XUUnityLightMcpGeneratedEditModeTargetedFilterColdDiscoveryTests
    {
        [Test]
        public void FullyQualifiedTargetIsDiscoveredAfterRefresh()
        {
            Assert.That(true, Is.True);
        }
    }
}
EOF

run_step "project_refresh" \
  "$WRAPPER" request-project-refresh \
  --project-root "$PROJECT_ROOT" \
  --timeout-ms 180000

run_step "targeted_editmode" \
  "$WRAPPER" request-editmode-tests \
  --project-root "$PROJECT_ROOT" \
  --assembly-name "$ASSEMBLY_NAME" \
  --test-name "$FULL_TEST_NAME" \
  --timeout-ms 180000

python3 - "$TMP_DIR/targeted_editmode.json" "$FULL_TEST_NAME" <<'PY' || fail_step "targeted_editmode_parse"
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
full_test_name = sys.argv[2]
decoder = json.JSONDecoder()
candidates = []
text = path.read_text(encoding="utf-8")
for index, char in enumerate(text):
    if char != "{":
        continue
    try:
        value, _ = decoder.raw_decode(text[index:])
    except json.JSONDecodeError:
        continue
    if isinstance(value, dict):
        candidates.append(value)

response = next(
    (
        item
        for item in reversed(candidates)
        if item.get("payload_type") == "unity.tests.run_editmode" and item.get("payload_json")
    ),
    None,
)
if response is None:
    raise SystemExit("targeted EditMode request did not expose a top-level test response")
if response.get("status") != "ok":
    raise SystemExit(f"targeted EditMode transport status was {response.get('status')!r}")

payload = json.loads(response["payload_json"])
if payload.get("status") != "passed" or payload.get("test_verdict") != "passed":
    raise SystemExit(
        "targeted EditMode request did not pass after refresh: "
        f"status={payload.get('status')!r} test_verdict={payload.get('test_verdict')!r}"
    )
if int(payload.get("total") or 0) != 1 or int(payload.get("passed") or 0) != 1:
    raise SystemExit(
        "targeted EditMode request did not select exactly one passing test: "
        f"total={payload.get('total')!r} passed={payload.get('passed')!r}"
    )
if full_test_name not in str(payload.get("filter_summary") or ""):
    raise SystemExit("targeted EditMode response did not preserve the fully qualified filter summary")

print(
    json.dumps(
        {
            "status": payload.get("status"),
            "test_verdict": payload.get("test_verdict"),
            "total": payload.get("total"),
            "passed": payload.get("passed"),
            "filter_summary": payload.get("filter_summary"),
        },
        ensure_ascii=True,
    )
)
PY

echo "[pass] editmode-targeted-filter-cold-discovery test=$FULL_TEST_NAME"
