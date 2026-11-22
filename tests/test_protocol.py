"""Tests for the Winbot protocol helpers."""

from __future__ import annotations

from custom_components.ecovacs_winbot.winbot import redact


def test_redact_hides_robot_identifiers() -> None:
    """Serial number, device id and MAC are replaced; everything else is kept."""
    body = {
        "code": 0,
        "data": {
            "getRobotInfo": {"SN": "SERIAL", "MAC": "AABBCCDDEEFF", "DID": "device-id", "SVER": "2.6.0"},
            "getError": {"code": [0]},
            "list": [{"SN": "SERIAL"}],
        },
    }
    assert redact(body) == {
        "code": 0,
        "data": {
            "getRobotInfo": {
                "SN": "**REDACTED**",
                "MAC": "**REDACTED**",
                "DID": "**REDACTED**",
                "SVER": "2.6.0",
            },
            "getError": {"code": [0]},
            "list": [{"SN": "**REDACTED**"}],
        },
    }
    # The original is untouched; the integration still reads the serial for the device registry.
    assert body["data"]["getRobotInfo"]["SN"] == "SERIAL"
