"""Tests for how the Winbot coordinator holds and releases the connection."""

from __future__ import annotations

from collections.abc import Generator
from datetime import timedelta
import math
from unittest.mock import MagicMock, patch

from freezegun.api import FrozenDateTimeFactory
import pytest
from pytest_homeassistant.common import MockConfigEntry, async_fire_time_changed

from custom_components.ecovacs_winbot.const import IDLE_CHECK_INTERVAL, IDLE_RELEASE_AFTER
from custom_components.ecovacs_winbot.winbot import WinbotStatus
from homeassistant.components.bluetooth import BluetoothServiceInfoBleak
from homeassistant.core import HomeAssistant

IDLE = WinbotStatus(state="idle")
# Idle ticks that still check before the one that lets go.
CHECKS_BEFORE_RELEASE = math.ceil(IDLE_RELEASE_AFTER / IDLE_CHECK_INTERVAL) - 1


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


async def _tick(hass: HomeAssistant, freezer: FrozenDateTimeFactory, delta: timedelta) -> None:
    """Move time on."""
    freezer.tick(delta)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()


async def test_releases_idle_robot_after_30_minutes(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    mock_config_entry: MockConfigEntry,
    mock_robot: MagicMock,
) -> None:
    """Keep checking while idle, let go after IDLE_RELEASE_AFTER, and come back for a command."""
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    coordinator = mock_config_entry.runtime_data
    assert mock_robot.get_info.await_count == 1

    # Backup checks every 2 minutes while idle.
    for _ in range(CHECKS_BEFORE_RELEASE):
        await _tick(hass, freezer, IDLE_CHECK_INTERVAL)
    assert mock_robot.get_info.await_count == 1 + CHECKS_BEFORE_RELEASE
    assert not coordinator.released
    mock_robot.disconnect.assert_not_awaited()

    # The next tick is past IDLE_RELEASE_AFTER and lets go instead of checking.
    await _tick(hass, freezer, IDLE_CHECK_INTERVAL)
    assert coordinator.released
    mock_robot.disconnect.assert_awaited_once()
    assert mock_robot.get_info.await_count == 1 + CHECKS_BEFORE_RELEASE

    # No more checks while released, so nothing keeps the robot awake.
    mock_robot.is_connected = False
    for _ in range(5):
        await _tick(hass, freezer, IDLE_CHECK_INTERVAL)
    assert mock_robot.get_info.await_count == 1 + CHECKS_BEFORE_RELEASE

    # Using a control connects again and restarts the idle clock.
    await coordinator.async_run_command("spray_once")
    mock_robot.spray_once.assert_awaited_once()
    assert not coordinator.released


async def test_stays_connected_while_charging(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    mock_config_entry: MockConfigEntry,
    mock_robot: MagicMock,
) -> None:
    """Don't let go while charging; the idle clock starts when it's unplugged."""
    charging = WinbotStatus(state="idle", charging=True)
    mock_robot.get_info.return_value = charging
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    coordinator = mock_config_entry.runtime_data

    for _ in range(30):
        await _tick(hass, freezer, IDLE_CHECK_INTERVAL)
    assert not coordinator.released
    mock_robot.disconnect.assert_not_awaited()

    # Unplugged: released IDLE_RELEASE_AFTER later, not right away.
    mock_robot.get_info.return_value = IDLE
    await _tick(hass, freezer, IDLE_CHECK_INTERVAL)
    assert not coordinator.released
    for _ in range(CHECKS_BEFORE_RELEASE):
        await _tick(hass, freezer, IDLE_CHECK_INTERVAL)
    assert not coordinator.released
    await _tick(hass, freezer, IDLE_CHECK_INTERVAL)
    assert coordinator.released
