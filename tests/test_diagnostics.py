"""Tests for the Winbot diagnostics."""

from __future__ import annotations

from dataclasses import replace
from unittest.mock import MagicMock

from pytest_homeassistant.common import MockConfigEntry

from custom_components.ecovacs_winbot.diagnostics import async_get_config_entry_diagnostics
from homeassistant.core import HomeAssistant

from .conftest import IDLE

ROBOT_INFO = {
    "SN": "SERIAL",
    "MAC": "AABBCCDD0BC4",
    "DID": "device-id",
    "MID": "b7oysg",
    "VVER": "10.0.8",
    "SVER": "2.6.0",
    "BVER": "K13_V316.03.08",
}


async def test_diagnostics(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_robot: MagicMock,
) -> None:
    """Diagnostics include every version the robot reports and hide its identifiers."""
    mock_robot.get_info.return_value = replace(
        IDLE, serial_number="SERIAL", firmware="2.6.0", model_id="b7oysg", robot_info=ROBOT_INFO
    )
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    diagnostics = await async_get_config_entry_diagnostics(hass, mock_config_entry)

    assert diagnostics["entry_data"] == {"address": "**REDACTED**"}
    assert diagnostics["model"] == {"model_id": "b7oysg", "name": "Winbot W2 Pro Omni"}
    assert diagnostics["connection"]["connected"] is True
    assert diagnostics["robot_info"] == {
        "SN": "**REDACTED**",
        "MAC": "**REDACTED**",
        "DID": "**REDACTED**",
        "MID": "b7oysg",
        "VVER": "10.0.8",
        "SVER": "2.6.0",
        "BVER": "K13_V316.03.08",
    }
    assert diagnostics["status"]["serial_number"] == "**REDACTED**"
    assert diagnostics["status"]["firmware"] == "2.6.0"
    assert "SERIAL" not in str(diagnostics)
    assert "0B:C4" not in str(diagnostics)
