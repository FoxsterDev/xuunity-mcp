# Unity Package Path Moved

The production Unity package moved to the registry-native path:

```text
packages/com.xuunity.light-mcp
```

Use this Git UPM URL for new installs:

```text
https://github.com/FoxsterDev/xuunity-mcp.git?path=/packages/com.xuunity.light-mcp#v0.3.32
```

The old path was:

```text
templates/unity-package
```

Existing projects pinned to `v0.3.11` continue to work because that release tag
still contains the old package path. Update to `v0.3.12` or newer when you are
ready to use the registry-native package layout.
