from __future__ import annotations

from server_setup_common import *
from server_setup_uninstall import *
from server_setup_plan import *
from server_setup_apply import *
from server_setup_validation import *

import server_setup_uninstall as _server_setup_uninstall
import server_setup_common as _server_setup_common


def build_uninstall_plan(
    *,
    mode: str,
    project_roots: list[str] | None,
    workspace_root: str | None = None,
    recursive: bool = False,
    client: str | None = None,
    include_other_client_helpers: bool = False,
) -> dict[str, Any]:
    previous_detect_client_context = _server_setup_uninstall.detect_client_context
    previous_common_detect_client_context = _server_setup_common.detect_client_context
    try:
        _server_setup_uninstall.detect_client_context = detect_client_context
        _server_setup_common.detect_client_context = detect_client_context
        return _server_setup_uninstall.build_uninstall_plan(
            mode=mode,
            project_roots=project_roots,
            workspace_root=workspace_root,
            recursive=recursive,
            client=client,
            include_other_client_helpers=include_other_client_helpers,
        )
    finally:
        _server_setup_uninstall.detect_client_context = previous_detect_client_context
        _server_setup_common.detect_client_context = previous_common_detect_client_context


__all__ = [name for name in globals() if not name.startswith("__")]
