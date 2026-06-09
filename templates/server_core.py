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


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, ensure_ascii=True)
        handle.write("\n")


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
