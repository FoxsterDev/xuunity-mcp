#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class ToolInvocationError(Exception):
    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


def read_json(path: Path) -> Any:
    raw_bytes = path.read_bytes()
    is_utf16 = raw_bytes.startswith(b"\xff\xfe") or raw_bytes.startswith(b"\xfe\xff")
    try:
        if is_utf16:
            try:
                return json.loads(raw_bytes.decode("utf-16"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                try:
                    return json.loads(raw_bytes.decode("utf-8-sig"))
                except Exception:
                    raise exc
        else:
            try:
                return json.loads(raw_bytes.decode("utf-8-sig"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                try:
                    return json.loads(raw_bytes.decode("utf-16"))
                except Exception:
                    raise exc
    except json.JSONDecodeError as exc:
        raise json.JSONDecodeError(
            f"Failed to parse JSON in {path}: {exc.msg}",
            exc.doc,
            exc.pos
        ) from exc
    except UnicodeDecodeError as exc:
        raise UnicodeDecodeError(
            exc.encoding,
            exc.object,
            exc.start,
            exc.end,
            f"Failed to decode text in {path}: {exc.reason}"
        ) from exc


def write_json(path: Path, data: Any) -> None:
    """Publish atomically: pollers of `path` must never observe a partial file."""
    import os
    import time
    import uuid

    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, indent=2, ensure_ascii=True) + "\n"
    tmp_path = path.with_name(f"{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        tmp_path.write_text(payload, encoding="utf-8")
        for _ in range(5):
            try:
                os.replace(tmp_path, path)
                return
            except PermissionError:
                # Windows: a reader may briefly hold the destination open.
                time.sleep(0.05)
        path.write_text(payload, encoding="utf-8")
    finally:
        try:
            tmp_path.unlink()
        except OSError:
            pass


class ServerFunctionProxy:
    def __init__(self, name: str, fallback: Any):
        self._name = name
        self._fallback = fallback
        try:
            functools.update_wrapper(self, fallback)
        except Exception:
            pass

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        server = sys.modules.get("server")
        if server is not None:
            func = getattr(server, self._name, None)
            if func is not None and func is not self:
                return func(*args, **kwargs)
        return self._fallback(*args, **kwargs)


class TimeProxy:
    def __getattr__(self, name: str) -> Any:
        server = sys.modules.get("server")
        if server is not None and hasattr(server, "time"):
            t = getattr(server, "time")
            if not isinstance(t, TimeProxy):
                return getattr(t, name)
        import time
        return getattr(time, name)


def wrap_globals_with_proxies(module_globals: dict[str, Any], names: list[str]) -> None:
    for name in names:
        if name in module_globals:
            fallback = module_globals[name]
            if not isinstance(fallback, ServerFunctionProxy):
                module_globals[name] = ServerFunctionProxy(name, fallback)


import functools
import sys


def is_windows_like_host() -> bool:
    import os

    return (
        os.name == "nt"
        or sys.platform.startswith("win")
        or os.environ.get("OS") == "Windows_NT"
        or str(os.environ.get("MSYSTEM") or "").upper().startswith(("MINGW", "MSYS", "CYGWIN"))
    )


def launcher_command_name() -> str:
    """Launcher name for copy-paste recovery commands, matched to the host."""
    import os

    configured = str(os.environ.get("XUUNITY_LIGHT_UNITY_MCP_LAUNCHER_NAME") or "").strip()
    if configured:
        return configured
    return "xuunity_light_unity_mcp.cmd" if is_windows_like_host() else "xuunity_light_unity_mcp.sh"


def quoted_shell_path(path: Any) -> str:
    """Space-safe path literal: native form on Windows-like hosts, POSIX elsewhere."""
    from pathlib import PurePath

    value = path if isinstance(path, PurePath) else Path(path)
    rendered = str(value) if is_windows_like_host() else value.as_posix()
    return f'"{rendered}"'


def render_launcher_cli(subcommand: str, project_root: Any, *extra: str) -> str:
    """Copy-paste-safe recovery command: host-matched launcher, quoted path."""
    parts = [launcher_command_name(), subcommand, "--project-root", quoted_shell_path(project_root)]
    parts.extend(extra)
    return " ".join(parts)


def hidden_window_subprocess_kwargs() -> dict[str, Any]:
    """Keep short helper probes from flashing console windows on Windows GUI hosts."""
    import os
    import subprocess

    if os.name != "nt":
        return {}
    return {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)}


def reconfigure_stdio_utf8() -> None:
    """Force UTF-8 stdio regardless of host locale.

    MCP clients speak UTF-8, but Windows defaults piped stdio to the ANSI
    codepage: a non-ASCII byte on stdin kills serve_stdio mid-decode and
    non-ASCII CLI output raises UnicodeEncodeError on cp866/cp1251 consoles.
    """
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):
            pass
