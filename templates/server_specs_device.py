from __future__ import annotations

_SERIAL = {"type": "string", "description": "adb serial. Required when more than one device is attached."}
_PACKAGE = {"type": "string", "description": "Android application id."}
_ALLOW_MUTATING = {"type": "boolean", "default": False, "description": "Required for operations that change device state."}
_APPROVE = {
    "type": "boolean",
    "default": False,
    "description": "Required, with allowMutating, for operations that delete app data; the package must be listed under device.packages in the project's MCP runtime config.",
}

DEVICE_TOOLS: dict[str, dict] = {
    "unity_device_list": {
        "description": "List attached Android devices through host-side adb (no editor round trip): serial, state, model, and a remediation for unauthorized or offline devices.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "projectRoot": {"type": "string"},
                "describe": {"type": "boolean", "default": False, "description": "Also read model, OS version, resolution and orientation of each ready device."},
            },
            "required": ["projectRoot"],
        },
    },
    "unity_device_install": {
        "description": "Install an APK on an Android device (adb install -r), classify refusals (signature conflict, downgrade, conflicting provider) and, by default, compile the dex to verify so cold-start timing is not inflated by run-from-apk.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "projectRoot": {"type": "string"},
                "serial": _SERIAL,
                "apkPath": {"type": "string"},
                "package": _PACKAGE,
                "allowDowngrade": {"type": "boolean", "default": False},
                "uninstallFirst": {"type": "boolean", "default": False, "description": "Uninstall before installing (needed to replace a differently signed app); also needs approve=true."},
                "compileVerify": {"type": "boolean", "default": True},
                "allowMutating": _ALLOW_MUTATING,
                "approve": _APPROVE,
            },
            "required": ["projectRoot", "apkPath"],
        },
    },
    "unity_device_app": {
        "description": "Launch (cold, warm or hot, optional Unity command-line args, wait for a logcat marker, optional frame pacing), stop, inspect, clear data or uninstall an Android app.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "projectRoot": {"type": "string"},
                "operation": {"type": "string", "enum": ["launch", "stop", "info", "clear_data", "uninstall"]},
                "serial": _SERIAL,
                "package": _PACKAGE,
                "activity": {"type": "string", "description": "Activity class or package/activity; required with unityArgs. Defaults to device.packages.<package>.activity."},
                "unityArgs": {"type": "array", "items": {"type": "string"}, "description": "Unity player command-line args passed with -e unity."},
                "marker": {"type": "string", "description": "Logcat regex that marks the app as ready. Defaults to device.packages.<package>.readyMarker."},
                "mode": {"type": "string", "enum": ["cold", "warm", "hot"], "default": "cold"},
                "timeoutSeconds": {"type": "number", "default": 60},
                "tailSeconds": {"type": "number", "default": 0},
                "measureFrames": {"type": "boolean", "default": False},
                "allowMutating": _ALLOW_MUTATING,
                "approve": _APPROVE,
            },
            "required": ["projectRoot", "operation", "package"],
        },
    },
    "unity_device_logcat": {
        "description": "Capture logcat to a session file (optionally until a regex), then grep or tail captured files instead of the device ring buffer.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "projectRoot": {"type": "string"},
                "operation": {"type": "string", "enum": ["capture", "grep", "tail"]},
                "serial": _SERIAL,
                "durationSeconds": {"type": "number", "default": 10},
                "stopWhen": {"type": "string"},
                "clear": {"type": "boolean", "default": False},
                "bufferSize": {"type": "string", "description": "Optional logcat -G value such as 16M."},
                "path": {"type": "string", "description": "Captured file for grep or tail."},
                "pattern": {"type": "string"},
                "maxLines": {"type": "integer", "default": 50, "minimum": 1},
            },
            "required": ["projectRoot", "operation"],
        },
    },
    "unity_device_files": {
        "description": "List or pull files from an app's external files dir, Download or /data/local/tmp into a device session folder.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "projectRoot": {"type": "string"},
                "operation": {"type": "string", "enum": ["pull", "list"]},
                "serial": _SERIAL,
                "remotePath": {"type": "string"},
                "timeoutSeconds": {"type": "number", "default": 300},
            },
            "required": ["projectRoot", "operation", "remotePath"],
        },
    },
    "unity_device_screen": {
        "description": "Take a device screenshot (screencap) into a session folder and return it with the device descriptor (model, OS, resolution, orientation).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "projectRoot": {"type": "string"},
                "serial": _SERIAL,
                "buildRevision": {"type": "string"},
            },
            "required": ["projectRoot"],
        },
    },
    "unity_device_frame_pacing": {
        "description": "Sample SurfaceFlinger present timestamps of the app's surface for a fixed duration and return fps, gap percentiles, counts over 33/50/100/250/500 ms and the top gaps; sampling holes are reported, never counted as freezes.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "projectRoot": {"type": "string"},
                "serial": _SERIAL,
                "package": _PACKAGE,
                "durationSeconds": {"type": "number", "default": 10},
                "intervalSeconds": {"type": "number", "default": 1.0},
            },
            "required": ["projectRoot", "package"],
        },
    },
    "unity_device_metrics": {
        "description": "Snapshot app memory (dumpsys meminfo), thermal status and CPU share as structured JSON.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "projectRoot": {"type": "string"},
                "serial": _SERIAL,
                "package": _PACKAGE,
                "kinds": {"type": "array", "items": {"type": "string", "enum": ["meminfo", "thermal", "cpu"]}},
            },
            "required": ["projectRoot"],
        },
    },
    "unity_device_coldstart_ab": {
        "description": "Cold-start A/B harness: for each build install the APK (optional), compile the dex to verify, run N cold starts with frame pacing until the ready marker plus a tail, and return per-run ready time and the longest present gap before the marker, with medians per build.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "projectRoot": {"type": "string"},
                "serial": _SERIAL,
                "package": _PACKAGE,
                "activity": {"type": "string"},
                "marker": {"type": "string"},
                "builds": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "label": {"type": "string"},
                            "apkPath": {"type": "string", "description": "Omit to measure the installed build."},
                            "unityArgs": {"type": "array", "items": {"type": "string"}},
                        },
                    },
                },
                "runs": {"type": "integer", "default": 3, "minimum": 1},
                "timeoutSeconds": {"type": "number", "default": 60},
                "tailSeconds": {"type": "number", "default": 3},
                "sleepBetweenSeconds": {"type": "number", "default": 2},
                "measureFrames": {"type": "boolean", "default": True},
                "compileVerify": {"type": "boolean", "default": True},
                "allowDowngrade": {"type": "boolean", "default": False},
                "uninstallFirst": {"type": "boolean", "default": False},
                "registerArtifact": {"type": "boolean", "default": True},
                "includeFullPayload": {"type": "boolean", "default": False},
                "allowMutating": _ALLOW_MUTATING,
                "approve": _APPROVE,
            },
            "required": ["projectRoot", "package", "builds"],
        },
    },
}
