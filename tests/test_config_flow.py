"""Tests for the Ecovacs Winbot config flow."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pytest_homeassistant.common import MockConfigEntry
from pytest_homeassistant.components.bluetooth import inject_bluetooth_service_info

from custom_components.ecovacs_winbot.const import DOMAIN
from custom_components.ecovacs_winbot.winbot import WinbotConnectionError
from homeassistant.components.bluetooth import BluetoothServiceInfoBleak
from homeassistant.config_entries import SOURCE_BLUETOOTH, SOURCE_USER
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from .conftest import ADDRESS, TITLE, make_service_info

pytestmark = pytest.mark.usefixtures("mock_setup_entry")


async def _inject(hass: HomeAssistant, *infos: BluetoothServiceInfoBleak) -> None:
    for info in infos:
        inject_bluetooth_service_info(hass, info)
    await hass.async_block_till_done()


async def test_user_flow(
    hass: HomeAssistant, service_info: BluetoothServiceInfoBleak, mock_client: MagicMock
) -> None:
    """Pick a robot from the ones in range and get an entry."""
    await _inject(hass, service_info, make_service_info("11:22:33:44:55:66", "Speaker"))

    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    # Only Winbots are offered.
    assert list(result["data_schema"].schema[CONF_ADDRESS].container) == [ADDRESS]

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_ADDRESS: ADDRESS})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == TITLE
    assert result["data"] == {CONF_ADDRESS: ADDRESS}
    assert result["result"].unique_id == ADDRESS
    mock_client.get_info.assert_awaited_once()
    mock_client.disconnect.assert_awaited_once()


@pytest.mark.parametrize(
    ("side_effect", "error"),
    [
        (WinbotConnectionError("out of range"), "cannot_connect"),
        (RuntimeError("boom"), "unknown"),
    ],
)
async def test_user_flow_errors(
    hass: HomeAssistant,
    service_info: BluetoothServiceInfoBleak,
    mock_client: MagicMock,
    side_effect: Exception,
    error: str,
) -> None:
    """Show the error, close the connection, and recover once the robot answers."""
    await _inject(hass, service_info)
    mock_client.get_info.side_effect = side_effect

    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_ADDRESS: ADDRESS})
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {"base": error}
    mock_client.disconnect.assert_awaited_once()

    mock_client.get_info.side_effect = None
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_ADDRESS: ADDRESS})
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_user_flow_no_devices(hass: HomeAssistant) -> None:
    """Abort when nothing that looks like a Winbot is in range."""
    await _inject(hass, make_service_info("11:22:33:44:55:66", "Speaker"))

    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "no_devices_found"


async def test_user_flow_skips_configured_robot(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, service_info: BluetoothServiceInfoBleak
) -> None:
    """A robot that is already set up is not offered again."""
    mock_config_entry.add_to_hass(hass)
    await _inject(hass, service_info)

    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "no_devices_found"


@pytest.mark.usefixtures("mock_ble_device")
async def test_bluetooth_flow(
    hass: HomeAssistant, service_info: BluetoothServiceInfoBleak, mock_client: MagicMock
) -> None:
    """Confirm a discovered robot and get an entry."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_BLUETOOTH}, data=service_info
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "bluetooth_confirm"

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == TITLE
    assert result["data"] == {CONF_ADDRESS: ADDRESS}
    assert result["result"].unique_id == ADDRESS


@pytest.mark.usefixtures("mock_ble_device")
async def test_bluetooth_flow_cannot_connect(
    hass: HomeAssistant, service_info: BluetoothServiceInfoBleak, mock_client: MagicMock
) -> None:
    """Show an error when the discovered robot doesn't answer, and recover."""
    mock_client.get_info = AsyncMock(side_effect=WinbotConnectionError("busy"))

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_BLUETOOTH}, data=service_info
    )
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}

    mock_client.get_info = AsyncMock()
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_bluetooth_flow_not_a_winbot(hass: HomeAssistant) -> None:
    """Abort when discovery matches something that isn't a Winbot."""
    info = make_service_info("11:22:33:44:55:66", "Speaker")
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_BLUETOOTH}, data=info
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "not_supported"


async def test_bluetooth_flow_already_configured(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, service_info: BluetoothServiceInfoBleak
) -> None:
    """Abort when the discovered robot is already set up."""
    mock_config_entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_BLUETOOTH}, data=service_info
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_user_flow_robot_gone(hass: HomeAssistant, service_info: BluetoothServiceInfoBleak) -> None:
    """Show cannot_connect when the robot is no longer in range on submit."""
    await _inject(hass, service_info)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    with patch(
        "custom_components.ecovacs_winbot.config_flow.async_ble_device_from_address", return_value=None
    ):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_ADDRESS: ADDRESS})
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}
