"""Shared fixtures for the Ecovacs Winbot tests."""

from __future__ import annotations

from collections.abc import Generator
import time
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest
from pytest_homeassistant.common import MockConfigEntry
from pytest_homeassistant.components.bluetooth import (
    generate_advertisement_data,
    generate_ble_device,
)

from custom_components.ecovacs_winbot.const import DOMAIN
from custom_components.ecovacs_winbot.winbot import WinbotStatus
from homeassistant.components.bluetooth import BluetoothServiceInfoBleak
from homeassistant.const import CONF_ADDRESS

ADDRESS = "AA:BB:CC:DD:0B:C4"
NAME = "WINBOT_TEST_0001"
TITLE = "Winbot 0BC4"
IDLE = WinbotStatus(state="idle")


def make_service_info(address: str, name: str) -> BluetoothServiceInfoBleak:
    """Build a connectable advertisement as the Bluetooth integration reports it."""
    return BluetoothServiceInfoBleak(
        name=name,
        address=address,
        rssi=-60,
        manufacturer_data={},
        service_data={},
        service_uuids=[],
        source="local",
        device=generate_ble_device(address, name),
        advertisement=generate_advertisement_data(local_name=name),
        connectable=True,
        time=time.monotonic(),
        tx_power=-127,
    )


@pytest.fixture(autouse=True, scope="session")
def mock_bluez_history() -> Generator[None]:
    """Report no BlueZ advertisement history.

    The shared fixtures pretend to be Linux, but dbus-fast leaves its unpacker unset
    on other systems, so reading BlueZ history crashes when the tests run on macOS.
    """
    with patch(
        "bluetooth_adapters.systems.linux.LinuxAdapters.history",
        new_callable=PropertyMock,
        return_value={},
    ):
        yield


@pytest.fixture(autouse=True)
def auto_enable_bluetooth(enable_bluetooth: None) -> None:
    """Run every test with the Bluetooth integration mocked and loaded."""


@pytest.fixture
def service_info() -> BluetoothServiceInfoBleak:
    """Return the robot's advertisement."""
    return make_service_info(ADDRESS, NAME)


@pytest.fixture
def mock_config_entry() -> MockConfigEntry:
    """Return a config entry for one robot."""
    return MockConfigEntry(domain=DOMAIN, title=TITLE, unique_id=ADDRESS, data={CONF_ADDRESS: ADDRESS})


@pytest.fixture
def mock_setup_entry() -> Generator[AsyncMock]:
    """Skip setting the entry up after the flow creates it."""
    with patch("custom_components.ecovacs_winbot.async_setup_entry", return_value=True) as mock:
        yield mock


@pytest.fixture
def mock_client() -> Generator[MagicMock]:
    """Mock the robot's Bluetooth client used by the config flow."""
    with patch("custom_components.ecovacs_winbot.config_flow.WinbotClient", autospec=True) as cls:
        yield cls.return_value


@pytest.fixture
def mock_ble_device(service_info: BluetoothServiceInfoBleak) -> Generator[None]:
    """Let the config flow find the robot without injecting its advertisement.

    Injecting it would start a discovery flow, and those wait until Home Assistant
    has started, which the test instance never does.
    """
    with patch(
        "custom_components.ecovacs_winbot.config_flow.async_ble_device_from_address",
        return_value=service_info.device,
    ):
        yield


@pytest.fixture
def mock_robot(service_info: BluetoothServiceInfoBleak) -> Generator[MagicMock]:
    """Mock the coordinator's client: an idle robot, in range, that answers getInfo.

    Presence is patched rather than injected: with frozen time the Bluetooth
    stack's own availability tracking would decide the robot went away.
    """
    with (
        patch("custom_components.ecovacs_winbot.coordinator.WinbotClient", autospec=True) as cls,
        patch(
            "custom_components.ecovacs_winbot.coordinator.bluetooth.async_address_present",
            return_value=True,
        ),
        patch(
            "custom_components.ecovacs_winbot.coordinator.bluetooth.async_ble_device_from_address",
            return_value=service_info.device,
        ),
    ):
        client = cls.return_value
        client.is_connected = True
        client.get_info.return_value = IDLE
        client.status = IDLE
        yield client
