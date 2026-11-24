"""Tests for the Winbot protocol helpers."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from pytest_homeassistant.components.bluetooth import generate_ble_device

from custom_components.ecovacs_winbot.winbot import WinbotClient, WinbotStatus, redact
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
    assert stats.power_presses is None


def test_parse_stats_buttons() -> None:
    """The mapped key_count positions are named; a short or odd list gives None."""
    stats = parse_stats({"key_count": [1, 13, 11, 0, 152, 0]})
    assert (stats.power_presses, stats.mode_presses, stats.cable_reel_presses) == (13, 11, 152)
    stats = parse_stats({"key_count": [1, "x"]})
    assert (stats.power_presses, stats.mode_presses, stats.cable_reel_presses) == (None, None, None)


@pytest.mark.parametrize(("angle", "sent"), [(45, 45), (0, 360), (360, 360)])
async def test_move(angle: int, sent: int) -> None:
    """One wheelMove, as the app sends it; 0 goes out as 360, the app's value for up."""
    client = WinbotClient(generate_ble_device("AA:BB:CC:DD:0B:C4", "WINBOT_TEST_0001"))
    with patch.object(client, "send", AsyncMock()) as send:
        await client.move(angle, 3)
    send.assert_awaited_once_with("wheelMove", {"angle": sent, "speed": 3, "act": "move"})


async def test_drive_repeats_every_100_ms() -> None:
    """drive repeats wheelMove about every 100 ms for the duration; 0 sends it once."""
    client = WinbotClient(generate_ble_device("AA:BB:CC:DD:0B:C4", "WINBOT_TEST_0001"))
    with patch.object(client, "send", AsyncMock()) as send:
        await client.drive(90, 2, 0)
        assert send.await_count == 1
        send.reset_mock()
        await client.drive(90, 2, 0.35)
    # Sends at about 0, 0.1, 0.2 and 0.3 s; a slow test machine may fit one fewer.
    assert 3 <= send.await_count <= 4
    send.assert_awaited_with("wheelMove", {"angle": 90, "speed": 2, "act": "move"})
