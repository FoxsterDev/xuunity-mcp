#!/usr/bin/env python3
from __future__ import annotations

DEFAULT_BRIDGE_TRANSPORT = "file_ipc"
TCP_LOOPBACK_BRIDGE_TRANSPORT = "tcp_loopback"
DEFAULT_CONFIGURED_BRIDGE_TRANSPORT = TCP_LOOPBACK_BRIDGE_TRANSPORT
SUPPORTED_BRIDGE_TRANSPORTS = {
    DEFAULT_BRIDGE_TRANSPORT,
    TCP_LOOPBACK_BRIDGE_TRANSPORT,
}
DEFAULT_HEARTBEAT_MAX_AGE_SECONDS = 10
DEFAULT_IDLE_STABLE_CYCLES = 2
POST_RESET_RECOVERY_RESPONSE_KEY = "_xuunity_post_reset_recovery"
COMPILE_WARNING_SAMPLE_LIMIT = 20
COMPILE_RED_FAIL_FAST_OPERATIONS = frozenset(
    {
        "unity.tests.run_editmode",
        "unity.tests.run_playmode",
        "unity.playmode.set",
    }
)
