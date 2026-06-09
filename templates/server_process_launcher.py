#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

class ProcessLauncher:
    _entrypoint_path: Path | None = None

    @classmethod
    def configure(cls, entrypoint_path: Path) -> None:
        cls._entrypoint_path = entrypoint_path

    @classmethod
    def get_self_invocation_base_command(cls) -> list[str]:
        """
        Determines the most portable command prefix to invoke the current server context.
        Handles PyInstaller execution, argv[0] matching, or configured entrypoint.
        """
        # Case A: PyInstaller / cx_Freeze compiled executable
        if getattr(sys, "frozen", False):
            return [sys.executable]

        # Case B: Explicitly configured path from entrypoint
        if cls._entrypoint_path is not None:
            return [sys.executable, str(cls._entrypoint_path)]

        # Case C: Direct script execution checking argv[0]
        try:
            script_path = Path(sys.argv[0]).resolve()
            if script_path.name == "server.py" and script_path.is_file():
                return [sys.executable, str(script_path)]
        except Exception:
            pass

        # Fallback to sibling server.py
        main_file = Path(__file__).parent / "server.py"
        return [sys.executable, str(main_file.resolve())]
