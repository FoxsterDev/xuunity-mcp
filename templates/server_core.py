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
    encodings = ["utf-8-sig", "utf-16"]
    if raw_bytes.startswith(b"\xff\xfe"):
        encodings = ["utf-16", "utf-8-sig"]
    elif raw_bytes.startswith(b"\xfe\xff"):
        encodings = ["utf-16", "utf-8-sig"]

    last_error: Exception | None = None
    for encoding in encodings:
        try:
            return json.loads(raw_bytes.decode(encoding))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            last_error = exc
    if last_error is not None:
        raise last_error
    return json.loads(raw_bytes.decode("utf-8-sig"))


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
