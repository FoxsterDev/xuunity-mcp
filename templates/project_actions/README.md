# Project Action Templates

These templates are public-safe starting points for project-owned MCP actions.
Copy the relevant fragment into the consumer project's `project_actions.yaml`
and place the C# hook in a project Editor assembly that references
`XUUnity.LightMcp.Editor.ScenarioHooks`.

`config_applying_build.project_actions.yaml` and
`ConfigApplyingBuildActionHook.cs.template` show a config-applying build lane.
The project fills in its own menu path or zero-argument static build method so
the MCP action drives the same configured build path that humans use. This is
for projects where raw `unity_build_player` or `batch-build-player` would skip
profile application, signing setup, dependency generation, or other project
build-tool behavior.
