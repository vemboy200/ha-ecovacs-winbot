"""Tests for the Winbot protocol helpers."""

from __future__ import annotations

from custom_components.ecovacs_winbot.winbot import WinbotStatus, redact
from custom_components.ecovacs_winbot.winbot.models import apply_info, parse_stats


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


def test_robot_info_kept_whole() -> None:
    """getRobotInfo fills the firmware and model id and keeps the raw section, BVER and VVER included."""
    section = {"MID": "b7oysg", "SVER": "2.6.0", "BVER": "K13_V316.03.08", "VVER": "10.0.8"}
    status = apply_info(WinbotStatus(), {"getRobotInfo": section})
    assert status.firmware == "2.6.0"
    assert status.model_id == "b7oysg"
    assert status.robot_info == section


def test_parse_stats() -> None:
    """Only plain integer counters are read; everything is kept in raw."""
    data = {"charge_count": 31, "no_water_count": True, "fall_count": [0], "glass_area": 1600}
    stats = parse_stats(data)
    assert stats.charge_count == 31
    assert stats.no_water_count is None
    assert stats.fall_count is None
    assert stats.raw == data
