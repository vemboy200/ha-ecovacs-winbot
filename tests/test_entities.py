"""Tests for the Winbot entities."""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
import logging
from unittest.mock import MagicMock, patch

from freezegun.api import FrozenDateTimeFactory
import pytest
from pytest_homeassistant.common import (
    MockConfigEntry,
    async_fire_time_changed,
    mock_restore_cache,
    snapshot_platform,
)
from pytest_homeassistant.components.bluetooth import inject_bluetooth_service_info
from syrupy.assertion import SnapshotAssertion

from custom_components.ecovacs_winbot import PLATFORMS
from custom_components.ecovacs_winbot.const import ACTIVE_POLL_INTERVAL, IDLE_CHECK_INTERVAL
from custom_components.ecovacs_winbot.winbot import CleanMode, Frame, FrameKind, WinbotError, WinbotStatus
from custom_components.ecovacs_winbot.winbot.models import parse_stats
from homeassistant.components.bluetooth import BluetoothServiceInfoBleak
from homeassistant.components.button import DOMAIN as BUTTON_DOMAIN, SERVICE_PRESS
from homeassistant.components.number import (
    ATTR_VALUE,
    DOMAIN as NUMBER_DOMAIN,
    SERVICE_SET_VALUE,
)
from homeassistant.components.switch import DOMAIN as SWITCH_DOMAIN
from homeassistant.components.vacuum import (
    ATTR_FAN_SPEED,
    DOMAIN as VACUUM_DOMAIN,
    SERVICE_CLEAN_SPOT,
    SERVICE_PAUSE,
    SERVICE_RETURN_TO_BASE,
    SERVICE_SET_FAN_SPEED,
    SERVICE_START,
    SERVICE_STOP,
    VacuumActivity,
)
from homeassistant.const import (
    ATTR_ENTITY_ID,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
    STATE_OFF,
    STATE_ON,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
    Platform,
)
from homeassistant.core import HomeAssistant, State
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import entity_registry as er

from .conftest import ADDRESS, BURY_DATA, IDLE, NAME, make_service_info

VACUUM = "vacuum.winbot_0bc4"
STATUS = "sensor.winbot_0bc4_status"
SIGNAL = "sensor.winbot_0bc4_signal_strength"
OUT_OF_WATER = "binary_sensor.winbot_0bc4_out_of_water"
AUTO_SPRAY = "switch.winbot_0bc4_automatic_spraying"
APP_MODE = "switch.winbot_0bc4_let_the_app_connect"
VOLUME = "number.winbot_0bc4_voice_volume"
SPRAY = "button.winbot_0bc4_spray"
EVENT = "event.winbot_0bc4_cleaning"
CHARGE_COUNT = "sensor.winbot_0bc4_charge_count"
BUMPER = "event.winbot_0bc4_bumper"
LAST_TRIGGER = "sensor.winbot_0bc4_last_trigger"

READY = replace(IDLE, battery_level=4, charging=False, attached=True, auto_spray=True, volume=35)
CLEANING = replace(READY, state="clean", trigger="app", router="depth", motion_state="working")
PAUSED = replace(CLEANING, motion_state="pause")


async def _setup(hass: HomeAssistant, entry: MockConfigEntry, robot: MagicMock, status: WinbotStatus) -> None:
    """Set up the entry with the robot reporting this status."""
    robot.get_info.return_value = status
    robot.status = status
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


@pytest.mark.usefixtures("entity_registry_enabled_by_default")
@pytest.mark.parametrize("platform", PLATFORMS)
async def test_entities(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    snapshot: SnapshotAssertion,
    mock_config_entry: MockConfigEntry,
    mock_robot: MagicMock,
    platform: Platform,
) -> None:
    """Every entity and its state while the robot is on and idle."""
    with patch("custom_components.ecovacs_winbot.PLATFORMS", [platform]):
        await _setup(hass, mock_config_entry, mock_robot, READY)
    await snapshot_platform(hass, entity_registry, snapshot, mock_config_entry.entry_id)


@pytest.mark.parametrize(
    ("service", "data", "method", "kwargs"),
    [
        (SERVICE_START, {}, "start", {"mode": CleanMode.DEPTH, "border": True, "duration": 0}),
        (SERVICE_PAUSE, {}, "pause", {}),
        (SERVICE_STOP, {}, "stop", {}),
        (SERVICE_RETURN_TO_BASE, {}, "return_home", {}),
        (SERVICE_CLEAN_SPOT, {}, "start", {"mode": CleanMode.SPOT, "border": False, "duration": 0}),
    ],
)
async def test_vacuum_commands(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_robot: MagicMock,
    service: str,
    data: dict[str, str],
    method: str,
    kwargs: dict[str, object],
) -> None:
    """Each vacuum action sends its command."""
    await _setup(hass, mock_config_entry, mock_robot, READY)
    assert hass.states.get(VACUUM).state == VacuumActivity.IDLE

    await hass.services.async_call(VACUUM_DOMAIN, service, {ATTR_ENTITY_ID: VACUUM, **data}, blocking=True)

    getattr(mock_robot, method).assert_awaited_once_with(**kwargs)


async def test_vacuum_mode(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_robot: MagicMock,
) -> None:
    """Picking a mode while idle only selects it; Start then uses it."""
    await _setup(hass, mock_config_entry, mock_robot, READY)

    await hass.services.async_call(
        VACUUM_DOMAIN,
        SERVICE_SET_FAN_SPEED,
        {ATTR_ENTITY_ID: VACUUM, ATTR_FAN_SPEED: "10 minutes"},
        blocking=True,
    )
    mock_robot.start.assert_not_awaited()
    assert hass.states.get(VACUUM).attributes[ATTR_FAN_SPEED] == "10 minutes"

    await hass.services.async_call(VACUUM_DOMAIN, SERVICE_START, {ATTR_ENTITY_ID: VACUUM}, blocking=True)
    mock_robot.start.assert_awaited_once_with(mode=CleanMode.DEPTH, border=True, duration=10)

    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            VACUUM_DOMAIN,
            SERVICE_SET_FAN_SPEED,
            {ATTR_ENTITY_ID: VACUUM, ATTR_FAN_SPEED: "Turbo"},
            blocking=True,
        )


async def test_vacuum_while_cleaning(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_robot: MagicMock,
) -> None:
    """While cleaning, the reported mode shows, and picking another switches right away."""
    await _setup(hass, mock_config_entry, mock_robot, CLEANING)
    state = hass.states.get(VACUUM)
    assert state.state == VacuumActivity.CLEANING
    assert state.attributes[ATTR_FAN_SPEED] == "Deep"

    await hass.services.async_call(
        VACUUM_DOMAIN,
        SERVICE_SET_FAN_SPEED,
        {ATTR_ENTITY_ID: VACUUM, ATTR_FAN_SPEED: "Edge"},
        blocking=True,
    )
    mock_robot.start.assert_awaited_once_with(mode=CleanMode.BORDER, border=False, duration=0)


async def test_vacuum_resumes_when_paused(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_robot: MagicMock,
) -> None:
    """Start resumes a paused clean instead of starting a new one."""
    await _setup(hass, mock_config_entry, mock_robot, PAUSED)
    assert hass.states.get(VACUUM).state == VacuumActivity.PAUSED

    await hass.services.async_call(VACUUM_DOMAIN, SERVICE_START, {ATTR_ENTITY_ID: VACUUM}, blocking=True)

    mock_robot.resume.assert_awaited_once_with()
    mock_robot.start.assert_not_awaited()


async def test_vacuum_error(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_robot: MagicMock,
) -> None:
    """Reported error codes show as the error activity."""
    await _setup(hass, mock_config_entry, mock_robot, replace(READY, error_codes=(102,)))
    assert hass.states.get(VACUUM).state == VacuumActivity.ERROR


@pytest.mark.parametrize(
    ("domain", "service", "entity_id", "data", "method", "args"),
    [
        (VACUUM_DOMAIN, SERVICE_START, VACUUM, {}, "start", ()),
        (SWITCH_DOMAIN, SERVICE_TURN_OFF, AUTO_SPRAY, {}, "set_auto_spray", (False,)),
        (SWITCH_DOMAIN, SERVICE_TURN_ON, AUTO_SPRAY, {}, "set_auto_spray", (True,)),
        (NUMBER_DOMAIN, SERVICE_SET_VALUE, VOLUME, {ATTR_VALUE: 21}, "set_volume", (21,)),
        (BUTTON_DOMAIN, SERVICE_PRESS, SPRAY, {}, "spray_once", ()),
    ],
)
async def test_commands_and_failures(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_robot: MagicMock,
    domain: str,
    service: str,
    entity_id: str,
    data: dict[str, object],
    method: str,
    args: tuple[object, ...],
) -> None:
    """Controls send their command, and a failed command is raised as a translated error."""
    await _setup(hass, mock_config_entry, mock_robot, READY)

    await hass.services.async_call(domain, service, {ATTR_ENTITY_ID: entity_id, **data}, blocking=True)
    command = getattr(mock_robot, method)
    if args:
        command.assert_awaited_once_with(*args)
    else:
        command.assert_awaited_once()

    command.side_effect = WinbotError("no reply")
    with pytest.raises(HomeAssistantError) as err:
        await hass.services.async_call(domain, service, {ATTR_ENTITY_ID: entity_id, **data}, blocking=True)
    assert err.value.translation_key == "command_failed"


async def test_app_mode(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_robot: MagicMock,
) -> None:
    """Letting the app connect disconnects HA and disables the controls until it's turned off."""
    await _setup(hass, mock_config_entry, mock_robot, READY)

    await hass.services.async_call(SWITCH_DOMAIN, SERVICE_TURN_ON, {ATTR_ENTITY_ID: APP_MODE}, blocking=True)
    mock_robot.disconnect.assert_awaited_once()
    mock_robot.is_connected = False
    assert hass.states.get(APP_MODE).state == STATE_ON
    for entity_id in (VACUUM, AUTO_SPRAY, VOLUME, SPRAY):
        assert hass.states.get(entity_id).state == STATE_UNAVAILABLE

    get_info_calls = mock_robot.get_info.await_count
    await hass.services.async_call(SWITCH_DOMAIN, SERVICE_TURN_OFF, {ATTR_ENTITY_ID: APP_MODE}, blocking=True)
    await hass.async_block_till_done()
    assert hass.states.get(APP_MODE).state == STATE_OFF
    assert hass.states.get(VACUUM).state == VacuumActivity.IDLE
    assert mock_robot.get_info.await_count == get_info_calls + 1


async def test_finished_event(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    mock_config_entry: MockConfigEntry,
    mock_robot: MagicMock,
) -> None:
    """The event entity fires when a clean ends on its own."""
    await _setup(hass, mock_config_entry, mock_robot, CLEANING)
    assert hass.states.get(EVENT).state == STATE_UNKNOWN

    mock_robot.get_info.return_value = replace(READY, trigger="workComplete")
    freezer.tick(ACTIVE_POLL_INTERVAL)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    state = hass.states.get(EVENT)
    assert state.state != STATE_UNKNOWN
    assert state.attributes["event_type"] == "finished"


async def test_robot_off_and_back(
    hass: HomeAssistant,
    caplog: pytest.LogCaptureFixture,
    mock_config_entry: MockConfigEntry,
    mock_robot: MagicMock,
    mock_robot_class: MagicMock,
    service_info: BluetoothServiceInfoBleak,
) -> None:
    """When the robot goes off, the status shows Off, the rest is unavailable, and both changes are logged once."""
    await _setup(hass, mock_config_entry, mock_robot, CLEANING)
    on_disconnect = mock_robot_class.call_args.kwargs["on_disconnect"]
    caplog.set_level(logging.INFO)

    # The connection drops and the robot is gone too: it went off mid-clean.
    mock_robot.is_connected = False
    with patch(
        "custom_components.ecovacs_winbot.coordinator.bluetooth.async_address_present",
        return_value=False,
    ):
        on_disconnect()
        await hass.async_block_till_done()

    assert hass.states.get(STATUS).state == "off"
    assert hass.states.get(VACUUM).state == STATE_UNAVAILABLE
    assert hass.states.get(EVENT).attributes["event_type"] == "interrupted"
    assert caplog.text.count("robot is off") == 1

    # It advertises again.
    mock_robot.get_info.return_value = READY
    inject_bluetooth_service_info(hass, service_info)
    await hass.async_block_till_done()
    assert hass.states.get(VACUUM).state == VacuumActivity.IDLE
    assert caplog.text.count("robot is back on") == 1


async def test_out_of_water_restored(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_robot: MagicMock,
) -> None:
    """Out of water is only pushed during a clean, so the last value survives a restart."""
    mock_restore_cache(hass, [State(OUT_OF_WATER, STATE_ON)])
    await _setup(hass, mock_config_entry, mock_robot, IDLE)
    assert hass.states.get(OUT_OF_WATER).state == STATE_ON


async def test_pushes(
    hass: HomeAssistant,
    caplog: pytest.LogCaptureFixture,
    mock_config_entry: MockConfigEntry,
    mock_robot: MagicMock,
    mock_robot_class: MagicMock,
) -> None:
    """Pushes update the entities; errors fire the event, and unknown messages are logged for reporting."""
    await _setup(hass, mock_config_entry, mock_robot, READY)
    on_status = mock_robot_class.call_args.kwargs["on_status"]

    on_status(CLEANING, Frame(FrameKind.PUSH, "onCleanInfo", None, {}, crc_ok=True))
    await hass.async_block_till_done()
    assert hass.states.get(VACUUM).state == VacuumActivity.CLEANING

    on_status(
        replace(CLEANING, error_codes=(102,), trigger="newTrigger"),
        Frame(FrameKind.PUSH, "onNewThing", None, {"data": {"SN": "SERIAL"}}, crc_ok=True),
    )
    await hass.async_block_till_done()
    event = hass.states.get(EVENT)
    assert event.attributes["event_type"] == "error"
    assert event.attributes["error_codes"] == [102]
    assert "doesn't know yet, please report it: onNewThing" in caplog.text
    assert "doesn't know yet, please report it: newTrigger" in caplog.text
    assert "SERIAL" not in caplog.text


@pytest.mark.parametrize("source", ["button", "app"])
async def test_started_event(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_robot: MagicMock,
    mock_robot_class: MagicMock,
    source: str,
) -> None:
    """The event entity fires when a clean starts, with where it was started from."""
    await _setup(hass, mock_config_entry, mock_robot, READY)
    on_status = mock_robot_class.call_args.kwargs["on_status"]

    on_status(replace(CLEANING, trigger=source), Frame(FrameKind.PUSH, "onCleanInfo", None, {}, crc_ok=True))
    await hass.async_block_till_done()
    event = hass.states.get(EVENT)
    assert event.attributes["event_type"] == "started"
    assert event.attributes["source"] == source

    # Resuming after a pause isn't a new start.
    fired = event.state
    on_status(PAUSED, Frame(FrameKind.PUSH, "onCleanInfo", None, {}, crc_ok=True))
    on_status(CLEANING, Frame(FrameKind.PUSH, "onCleanInfo", None, {}, crc_ok=True))
    await hass.async_block_till_done()
    assert hass.states.get(EVENT).state == fired


async def test_no_started_event_on_first_status(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_robot: MagicMock,
) -> None:
    """A clean already running when HA connects isn't reported as started."""
    await _setup(hass, mock_config_entry, mock_robot, CLEANING)
    assert hass.states.get(EVENT).state == STATE_UNKNOWN


async def test_out_of_water_event(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_robot: MagicMock,
    mock_robot_class: MagicMock,
) -> None:
    """The event entity fires once when the robot reports out of water."""
    await _setup(hass, mock_config_entry, mock_robot, CLEANING)
    on_status = mock_robot_class.call_args.kwargs["on_status"]
    dry = replace(CLEANING, out_of_water=True)

    on_status(dry, Frame(FrameKind.PUSH, "onSprayInfo", None, {}, crc_ok=True))
    await hass.async_block_till_done()
    event = hass.states.get(EVENT)
    assert event.attributes["event_type"] == "out_of_water"
    assert hass.states.get(OUT_OF_WATER).state == STATE_ON

    on_status(dry, Frame(FrameKind.PUSH, "onSprayInfo", None, {}, crc_ok=True))
    await hass.async_block_till_done()
    assert hass.states.get(EVENT).state == event.state  # not again while still out of water


@pytest.mark.parametrize("entity_id", [BUMPER, LAST_TRIGGER])
async def test_disabled_by_default(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    mock_config_entry: MockConfigEntry,
    mock_robot: MagicMock,
    entity_id: str,
) -> None:
    """Entities that are rarely useful in automations are disabled by default."""
    await _setup(hass, mock_config_entry, mock_robot, READY)
    assert entity_registry.async_get(entity_id).disabled_by is er.RegistryEntryDisabler.INTEGRATION
    assert hass.states.get(entity_id) is None


@pytest.mark.usefixtures("entity_registry_enabled_by_default")
@pytest.mark.parametrize(
    ("trigger", "state"), [("button", "button"), ("workComplete", "workComplete"), ("new", STATE_UNKNOWN)]
)
async def test_last_trigger(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_robot: MagicMock,
    trigger: str,
    state: str,
) -> None:
    """The last trigger sensor shows known triggers, and unknown for new ones (those are logged instead)."""
    await _setup(hass, mock_config_entry, mock_robot, replace(READY, trigger=trigger))
    assert hass.states.get(LAST_TRIGGER).state == state


@pytest.mark.usefixtures("entity_registry_enabled_by_default")
async def test_bumper_event(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_robot: MagicMock,
    mock_robot_class: MagicMock,
) -> None:
    """A collision push fires the bumper event with the robot's code, and not the cleaning event."""
    await _setup(hass, mock_config_entry, mock_robot, READY)
    on_status = mock_robot_class.call_args.kwargs["on_status"]

    on_status(READY, Frame(FrameKind.PUSH, "onCollision", None, {"data": {"direction": "br,"}}, crc_ok=True))
    await hass.async_block_till_done()
    bumper = hass.states.get(BUMPER)
    assert bumper.attributes["event_type"] == "bumped"
    assert bumper.attributes["code"] == "br,"
    assert hass.states.get(EVENT).state == STATE_UNKNOWN


async def test_reconnects_after_drop(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_robot: MagicMock,
    mock_robot_class: MagicMock,
) -> None:
    """A dropped connection while the robot is still on is picked up again right away."""
    await _setup(hass, mock_config_entry, mock_robot, CLEANING)
    on_disconnect = mock_robot_class.call_args.kwargs["on_disconnect"]
    calls = mock_robot.get_info.await_count

    on_disconnect()
    await hass.async_block_till_done()

    assert mock_robot.get_info.await_count == calls + 1
    assert hass.states.get(VACUUM).state == VacuumActivity.CLEANING


@pytest.mark.parametrize(
    ("status", "app_mode", "interval"),
    [
        pytest.param(READY, False, IDLE_CHECK_INTERVAL, id="idle"),
        pytest.param(CLEANING, False, ACTIVE_POLL_INTERVAL, id="cleaning"),
        pytest.param(READY, True, IDLE_CHECK_INTERVAL, id="app_mode"),
    ],
)
async def test_signal_strength(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    mock_config_entry: MockConfigEntry,
    mock_robot: MagicMock,
    status: WinbotStatus,
    app_mode: bool,
    interval: timedelta,
) -> None:
    """Signal strength is refreshed on a timer, whatever the robot is doing.

    The robot's advertisement content doesn't change while it's on, so a new
    reading alone doesn't reach the advertisement callback.
    """
    await _setup(hass, mock_config_entry, mock_robot, status)
    if app_mode:
        await hass.services.async_call(
            SWITCH_DOMAIN, SERVICE_TURN_ON, {ATTR_ENTITY_ID: APP_MODE}, blocking=True
        )
    assert hass.states.get(SIGNAL).state == STATE_UNAVAILABLE  # no advertisement seen yet

    for rssi in (-70, -75):
        with patch(
            "custom_components.ecovacs_winbot.coordinator.bluetooth.async_last_service_info",
            return_value=make_service_info(ADDRESS, NAME, rssi=rssi),
        ):
            freezer.tick(interval)
            async_fire_time_changed(hass)
            await hass.async_block_till_done()
        assert hass.states.get(SIGNAL).state == str(rssi)


async def test_statistics(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    mock_config_entry: MockConfigEntry,
    mock_robot: MagicMock,
) -> None:
    """Lifetime counters are read on connect and when charging starts, not on every check."""
    await _setup(hass, mock_config_entry, mock_robot, READY)
    assert mock_robot.get_stats.await_count == 1
    assert hass.states.get(CHARGE_COUNT).state == "31"

    freezer.tick(IDLE_CHECK_INTERVAL)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert mock_robot.get_stats.await_count == 1

    mock_robot.get_info.return_value = replace(READY, charging=True)
    mock_robot.get_stats.return_value = parse_stats({**BURY_DATA, "charge_count": 32})
    freezer.tick(IDLE_CHECK_INTERVAL)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert mock_robot.get_stats.await_count == 2
    assert hass.states.get(CHARGE_COUNT).state == "32"


async def test_statistics_retried(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    mock_config_entry: MockConfigEntry,
    mock_robot: MagicMock,
) -> None:
    """If reading the counters fails, they're read again on the next check."""
    mock_robot.get_stats.side_effect = WinbotError("no answer to getBuryData")
    await _setup(hass, mock_config_entry, mock_robot, READY)
    assert hass.states.get(CHARGE_COUNT).state == STATE_UNKNOWN

    mock_robot.get_stats.side_effect = None
    freezer.tick(IDLE_CHECK_INTERVAL)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass.states.get(CHARGE_COUNT).state == "31"


async def test_retired_entities_removed(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    mock_config_entry: MockConfigEntry,
    mock_robot: MagicMock,
) -> None:
    """Entities from earlier versions are removed on setup."""
    mock_config_entry.add_to_hass(hass)
    old = entity_registry.async_get_or_create(
        Platform.BUTTON, "ecovacs_winbot", f"{ADDRESS}_start", config_entry=mock_config_entry
    )
    await _setup(hass, mock_config_entry, mock_robot, READY)
    assert entity_registry.async_get(old.entity_id) is None
