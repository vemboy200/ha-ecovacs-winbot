"""Connection manager for one Winbot.

HA stays connected whenever the robot is on, so it gets every push (start,
error, finished) the moment it happens, however the clean was started. The
robot accepts one Bluetooth connection at a time, so the "Let the app connect"
switch makes HA let go for the ECOVACS HOME app. Whether the robot is on comes
from its advertisements.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
import logging
import time

from homeassistant.components import bluetooth
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    ACTIVE_POLL_INTERVAL,
    DOMAIN,
    EVENT_ERROR,
    EVENT_FINISHED,
    EVENT_INTERRUPTED,
    FALLBACK_AVAILABILITY_SECONDS,
    IDLE_CHECK_INTERVAL,
)
from .winbot import Frame, WinbotClient, WinbotError, WinbotStatus

_LOGGER = logging.getLogger(__name__)

type WinbotConfigEntry = ConfigEntry[WinbotCoordinator]

# Push messages seen so far (docs/protocol.md). Anything else gets logged as a warning.
KNOWN_TRIGGERS = {"button", "app", "workComplete"}
KNOWN_PUSHES = {"onBatteryInfo", "onCleanInfo", "onAdsorption", "onGlassType", "onSprayInfo"}


class WinbotCoordinator(DataUpdateCoordinator[WinbotStatus]):
    """Keep track of one robot: awake/asleep, connection, status, events."""

    config_entry: WinbotConfigEntry

    def __init__(self, hass: HomeAssistant, entry: WinbotConfigEntry, address: str) -> None:
        """Initialize."""
        super().__init__(hass, _LOGGER, config_entry=entry, name=DOMAIN, update_interval=None)
        self.address = address
        self.awake = bluetooth.async_address_present(hass, address, connectable=True)
        self.app_mode = False  # True = HA lets go so the app can connect
        self.client: WinbotClient | None = None
        self._lock = asyncio.Lock()
        self._unsubs: list[CALLBACK_TYPE] = []
        self._active_poll: CALLBACK_TYPE | None = None
        self._event_listeners: list[Callable[[str, dict[str, object] | None], None]] = []
        self.data = WinbotStatus()
        self.rssi: int | None = None
        self._device_info_written: tuple[str | None, str | None] = (None, None)
        self._rssi_written: tuple[int | None, float] = (None, 0.0)

    # Lifecycle

    @callback
    def async_start(self) -> None:
        """Start listening for advertisements."""
        bluetooth.async_set_fallback_availability_interval(
            self.hass, self.address, FALLBACK_AVAILABILITY_SECONDS
        )
        self._unsubs.append(
            bluetooth.async_register_callback(
                self.hass,
                self._async_on_advertisement,
                bluetooth.BluetoothCallbackMatcher(address=self.address, connectable=True),
                bluetooth.BluetoothScanningMode.ACTIVE,
            )
        )
        self._unsubs.append(
            bluetooth.async_track_unavailable(
                self.hass, self._async_on_unavailable, self.address, connectable=True
            )
        )
        # Backup status check, and a reconnect if the connection dropped. A timer,
        # because HA only calls _async_on_advertisement when the advertisement
        # content changes, and the robot's doesn't while it sits idle.
        self._unsubs.append(async_track_time_interval(self.hass, self._async_idle_tick, IDLE_CHECK_INTERVAL))
        if self.awake:
            self._schedule_check()

    @callback
    def _async_idle_tick(self, _now: object) -> None:
        if self.awake and not self.data.is_active:  # the active poll covers cleaning
            if info := bluetooth.async_last_service_info(self.hass, self.address, connectable=True):
                self.rssi = info.rssi
            self._schedule_check()

    async def async_shutdown(self) -> None:
        """Stop everything and disconnect."""
        await super().async_shutdown()
        for unsub in self._unsubs:
            unsub()
        self._unsubs.clear()
        self._stop_active_poll()
        if self.client:
            await self.client.disconnect()

    # Events (finished / interrupted)

    @callback
    def async_add_event_listener(
        self, listener: Callable[[str, dict[str, object] | None], None]
    ) -> CALLBACK_TYPE:
        """Listen for robot events. Returns an unsubscribe callback."""
        self._event_listeners.append(listener)
        return lambda: self._event_listeners.remove(listener)

    @callback
    def _fire(self, event_type: str, attributes: dict[str, object] | None = None) -> None:
        _LOGGER.debug("%s: event %s %s", self.address, event_type, attributes)
        for listener in list(self._event_listeners):
            listener(event_type, attributes)

    # Bluetooth callbacks

    @callback
    def _async_on_advertisement(
        self, service_info: bluetooth.BluetoothServiceInfoBleak, change: bluetooth.BluetoothChange
    ) -> None:
        if self.client:
            self.client.set_ble_device(service_info.device)
        self.rssi = service_info.rssi
        was_awake, self.awake = self.awake, True
        if not was_awake:
            _LOGGER.debug("%s: robot is on", self.address)
            self._rssi_written = (self.rssi, time.monotonic())
            self.async_update_listeners()
            self._schedule_check()
            return
        self._maybe_write_rssi()

    @callback
    def _maybe_write_rssi(self) -> None:
        """Update entities when the signal moved by 3 dB or more, or every 60 s.

        Advertisements arrive several times a second; writing state on each one would flood the recorder.
        """
        last_rssi, last_time = self._rssi_written
        now = time.monotonic()
        if self.rssi is None or (
            last_rssi is not None and abs(self.rssi - last_rssi) < 3 and now - last_time < 60
        ):
            return
        self._rssi_written = (self.rssi, now)
        self.async_update_listeners()

    @callback
    def _async_on_unavailable(self, _service_info: bluetooth.BluetoothServiceInfoBleak) -> None:
        if self._connected:
            return  # still talking to it; advertisements may pause while connected
        self._mark_off()

    @callback
    def _mark_off(self) -> None:
        if not self.awake:
            return
        _LOGGER.debug("%s: robot is off (no advertisements)", self.address)
        if self.data.is_active:
            self._fire(EVENT_INTERRUPTED)
        self.awake = False
        self.async_update_listeners()

    @callback
    def _on_unexpected_disconnect(self) -> None:
        _LOGGER.debug("%s: connection dropped", self.address)
        self._stop_active_poll()
        if not bluetooth.async_address_present(self.hass, self.address, connectable=True):
            # The unavailable callback was skipped while connected, so check here.
            self._mark_off()
            return
        self._schedule_check()  # get back in
        self.async_update_listeners()

    @callback
    def _on_status(self, status: WinbotStatus, frame: Frame) -> None:
        """Handle a push from the robot."""
        if frame.command not in KNOWN_PUSHES:
            # Still learning the protocol (errors especially): make new messages easy to spot and report.
            _LOGGER.warning(
                "Winbot sent a message this integration doesn't know yet, please report it: %s %s",
                frame.command,
                frame.body,
            )
        self._handle_new_status(status)

    # Core logic

    @property
    def _connected(self) -> bool:
        return self.client is not None and self.client.is_connected

    @property
    def connected(self) -> bool:
        """Return True while HA holds the Bluetooth connection."""
        return self._connected

    @callback
    def _handle_new_status(self, status: WinbotStatus) -> None:
        old = self.data
        if status.error_codes != old.error_codes and any(status.error_codes):
            # Error codes aren't mapped to meanings yet; log them with the context we have.
            _LOGGER.warning(
                "Winbot reported error codes %s (state %s, trigger %s, mode %s)",
                list(status.error_codes),
                status.state,
                status.trigger,
                status.router,
            )
            if old.state is not None:  # not on the first status after setup, or every restart would fire it
                self._fire(EVENT_ERROR, {"error_codes": list(status.error_codes)})
        if (
            status.trigger is not None
            and status.trigger != old.trigger
            and status.trigger not in KNOWN_TRIGGERS
        ):
            _LOGGER.warning(
                "Winbot reported a trigger this integration doesn't know yet, please report it: %s (state %s)",
                status.trigger,
                status.state,
            )
        if status.finished and not old.finished and old.state is not None:
            self._fire(EVENT_FINISHED)
        self.async_set_updated_data(status)
        self._update_device_info(status)
        if status.is_active:
            self._start_active_poll()
        else:
            self._stop_active_poll()

    @callback
    def _schedule_check(self) -> None:
        if self.app_mode:
            return
        self.config_entry.async_create_background_task(
            self.hass, self._async_check(), f"{DOMAIN} check {self.address}", eager_start=True
        )

    async def _async_check(self) -> None:
        """Connect if needed, ask for the full status, then decide whether to stay."""
        if self._lock.locked():
            return
        async with self._lock:
            try:
                client = self._get_client()
                status = await client.get_info()
            except WinbotError as err:
                _LOGGER.debug("%s: status check failed: %s", self.address, err)
                return
            self._handle_new_status(status)

    def _get_client(self) -> WinbotClient:
        ble_device = bluetooth.async_ble_device_from_address(self.hass, self.address, connectable=True)
        if ble_device is None:
            raise WinbotError("robot not in range of a connectable Bluetooth adapter or proxy")
        if self.client is None:
            self.client = WinbotClient(
                ble_device, on_status=self._on_status, on_disconnect=self._on_unexpected_disconnect
            )
        else:
            self.client.set_ble_device(ble_device)
        return self.client

    @callback
    def _start_active_poll(self) -> None:
        if self._active_poll is None:
            self._active_poll = async_track_time_interval(
                self.hass, self._async_active_poll_tick, ACTIVE_POLL_INTERVAL
            )

    @callback
    def _async_active_poll_tick(self, _now: object) -> None:
        self._schedule_check()

    @callback
    def _stop_active_poll(self) -> None:
        if self._active_poll:
            self._active_poll()
            self._active_poll = None

    @callback
    def _update_device_info(self, status: WinbotStatus) -> None:
        info = (status.serial_number, status.firmware)
        if not any(info) or info == self._device_info_written:
            return
        self._device_info_written = info
        # get_or_create updates the existing device and avoids the deprecated async_get_device lookup.
        dr.async_get(self.hass).async_get_or_create(
            config_entry_id=self.config_entry.entry_id,
            identifiers={(DOMAIN, self.address)},
            serial_number=status.serial_number,
            sw_version=status.firmware,
        )

    # Used by entities

    async def async_run_command(self, method: str, *args: object, **kwargs: object) -> None:
        """Run a client command (connecting first if needed)."""
        if self.app_mode:
            raise WinbotError("HA is paused so the app can connect")
        async with self._lock:
            client = self._get_client()
            if not client.is_connected:
                # Fresh connection: get the full status first, so the UI is
                # current right away and pause/stop use the real cleaning mode.
                self._handle_new_status(await client.get_info())
            await getattr(client, method)(*args, **kwargs)
        # The robot pushes onCleanInfo after clean commands; this covers a late push.
        self._handle_new_status(client.status)

    async def async_set_app_mode(self, enabled: bool) -> None:
        """Pause (True) or resume (False) HA's use of the connection."""
        self.app_mode = enabled
        if enabled:
            self._stop_active_poll()
            if self.client:
                await self.client.disconnect()
        elif self.awake:
            self._schedule_check()
        self.async_update_listeners()
