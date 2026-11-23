"""Tests for the robot's device entry."""

from __future__ import annotations

from dataclasses import replace
from unittest.mock import MagicMock, patch

import pytest
from pytest_homeassistant.common import MockConfigEntry

from custom_components.ecovacs_winbot.const import DOMAIN
from custom_components.ecovacs_winbot.winbot import WinbotConnectionError
from custom_components.ecovacs_winbot.winbot.products import model_id_from_name, model_name
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from .conftest import ADDRESS, IDLE, make_service_info


@pytest.mark.parametrize(
    ("model_id", "expected_model", "expected_model_id"),
    [
        ("b7oysg", "Winbot W2 Pro Omni", "b7oysg"),
        ("zzzzzz", "Winbot", "zzzzzz"),
    ],
)
async def test_model_from_robot(
    hass: HomeAssistant,
    device_registry: dr.DeviceRegistry,
    mock_config_entry: MockConfigEntry,
    mock_robot: MagicMock,
    model_id: str,
    expected_model: str,
    expected_model_id: str,
) -> None:
    """The model id the robot reports becomes the device's model id and, when known, its model name."""
    mock_robot.get_info.return_value = replace(
        IDLE, serial_number="SERIAL", firmware="2.6.0", model_id=model_id
    )
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    device = device_registry.async_get_device_by_identifier((DOMAIN, ADDRESS), mock_config_entry.entry_id)
    assert device is not None
    assert device.model == expected_model
    assert device.model_id == expected_model_id
    assert device.sw_version == "2.6.0"


async def test_model_from_advertised_name(
    hass: HomeAssistant,
    device_registry: dr.DeviceRegistry,
    mock_config_entry: MockConfigEntry,
    mock_robot: MagicMock,
) -> None:
    """Before the robot answers, the model comes from its advertised name."""
    mock_robot.get_info.side_effect = WinbotConnectionError("out of range")
    with patch(
        "custom_components.ecovacs_winbot.coordinator.bluetooth.async_last_service_info",
        return_value=make_service_info(ADDRESS, "WINBOT_b7oysg_0001"),
    ):
        mock_config_entry.add_to_hass(hass)
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    device = device_registry.async_get_device_by_identifier((DOMAIN, ADDRESS), mock_config_entry.entry_id)
    assert device is not None
    assert device.model == "Winbot W2 Pro Omni"
    assert device.model_id == "b7oysg"


def test_model_lookup_helpers() -> None:
    """Model ids are read from the advertised name and looked up by name."""
    assert model_id_from_name("WINBOT_b7oysg_0001") == "b7oysg"
    assert model_id_from_name("WINBASE_b7oysg_0001") is None
    assert model_id_from_name(None) is None
    assert model_name("99iw23") == "Winbot W3 Omni"
    assert model_name("unknown") is None
    assert model_name(None) is None
