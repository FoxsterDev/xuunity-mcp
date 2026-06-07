# Demo Video Production Plan

Date: `2026-06-07`
Status: `ready to record`

The homepage currently uses `docs/assets/xuunity-demo-storyboard.svg` as a
video-ready storyboard poster with a crawlable transcript. A real `.mp4` or
`.webm` should replace the poster module when a screen recording tool is
available.

## Target Asset

Recommended output:

```text
docs/assets/xuunity-mcp-demo.webm
```

Fallback output:

```text
docs/assets/xuunity-mcp-demo.mp4
```

## Runtime

- Length: 45-75 seconds
- Aspect ratio: 16:9
- Style: terminal-first, with brief Unity Editor status/result cuts
- Goal: show proof-oriented workflow, not broad editor mutation

## Shot List

1. `setup-plan` produces a preflight review with project and client config
   changes.
2. User approves, then `setup-apply` applies only the approved target.
3. `validate-setup` confirms helper, package, bridge, and client wiring.
4. `ensure-ready` brings Unity Editor to a ready state.
5. First live `unity_status_summary` proves the MCP bridge is healthy.
6. Compile matrix and test lanes produce validation evidence.
7. Closeout shows command results, artifacts, and restored editor state.

## Voiceover / Caption Script

```text
XUUnity MCP is a lightweight Unity MCP server for safe Unity Editor automation.
The workflow starts with setup-plan, so an AI agent can show the exact files
and client config that would change before mutation. After approval, setup-apply
wires only the selected Unity project. validate-setup and ensure-ready confirm
the bridge is healthy before live MCP tools run. From there, the agent can run
compile validation, EditMode tests, PlayMode tests, scene assertions, and
screenshots. The result is not just editor control; it is engineering evidence.
```

## Homepage Integration

After recording, update the homepage demo section to use:

```html
<video controls poster="assets/xuunity-demo-storyboard.svg">
  <source src="assets/xuunity-mcp-demo.webm" type="video/webm">
</video>
```

Keep the existing transcript summary below the video for search indexing and
accessibility.
