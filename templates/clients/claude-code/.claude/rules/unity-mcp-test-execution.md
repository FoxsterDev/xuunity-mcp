# Unity MCP Test Execution Rules

When xuunity-light-unity-mcp is available, use MCP commands. Fallback to Unity CLI if MCP unavailable.

## MCP Commands
- EditMode batch: batch-editmode-tests --project-root <path>
- EditMode interactive: ensure-ready --open-editor --project-root <path> then request-editmode-tests --project-root <path>
- PlayMode interactive: ensure-ready --open-editor --project-root <path> then request-playmode-tests --project-root <path>

## Unity CLI Alternative
- EditMode batch: Unity -runTests -testPlatform editmode -batchmode -projectPath <path>
- PlayMode batch: Unity -runTests -testPlatform playmode -batchmode -projectPath <path>
- Use when MCP bridge unavailable or not installed

## Bridge Health Requirements
Always run ensure-ready before MCP requests. Check unity.status if issues occur. Use project-discovery-report for diagnostics. Use recover-editor-session for stale state.

## Test Framework Installation
MCP offline: install-test-framework --yes --project-root <path> (edits manifest.json before Unity opens)
Manual: Edit Packages/manifest.json directly if MCP not available

## Examples

EditMode batch via MCP:
```bash
cd AIRoot/Operations/XUUnityLightUnityMcp
bash xuunity_light_unity_mcp.sh batch-editmode-tests --project-root /path/to/UnityProject
```

All tests via MCP interactive:
```bash
cd AIRoot/Operations/XUUnityLightUnityMcp
bash xuunity_light_unity_mcp.sh ensure-ready --project-root /path/to/UnityProject --open-editor --background-open
bash xuunity_light_unity_mcp.sh request-editmode-tests --project-root /path/to/UnityProject
bash xuunity_light_unity_mcp.sh request-playmode-tests --project-root /path/to/UnityProject
```

## Full Documentation
- AIRoot/Operations/XUUnityLightUnityMcp/docs/agents/AI_INTEGRATION.md
- AIRoot/Operations/XUUnityLightUnityMcp/docs/agents/AGENT_WORKFLOWS.md
