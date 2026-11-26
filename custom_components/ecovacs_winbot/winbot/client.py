"""BLE client for the Winbot: connect, request/reply, push callbacks, commands."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
import logging
import time
from typing import Any

from bleak import BleakClient
from bleak.backends.device import BLEDevice
from bleak.exc import BleakError
from bleak_retry_connector import (
    BleakClientWithServiceCache,
    establish_connection,
)

from .models import CleanMode, WinbotStats, WinbotStatus, apply_info, apply_section, parse_stats
from .protocol import Frame, FrameAssembler, FrameKind, encode_request, new_msg_id, redact

_LOGGER = logging.getLogger(__name__)

NOTIFY_UUID = "0000fff1-0000-1000-8000-00805f9b34fb"
WRITE_UUID = "0000fff2-0000-1000-8000-00805f9b34fb"
REQUEST_TIMEOUT = 8.0
WRITE_CHUNK = 180  # stays under any negotiated MTU we've seen
# The app repeats wheelMove about every 100 ms while its joystick is held. The robot stops
# by itself about 1.1 to 1.3 s after the last one (docs/protocol.md).
DRIVE_INTERVAL = 0.1


class WinbotError(Exception):
    """Base error."""


class WinbotConnectionError(WinbotError):
    """Could not connect or the connection dropped."""


class WinbotCommandError(WinbotError):
    """The robot answered a request with a non-zero code, or didn't answer."""


class WinbotClient:
    """One robot. Not thread-safe; use from one event loop."""

    def __init__(
        self,
        ble_device: BLEDevice,
        on_status: Callable[[WinbotStatus, Frame], None] | None = None,
        on_disconnect: Callable[[], None] | None = None,
    ) -> None:
        """Initialize the client."""
        self._ble_device = ble_device
        self._on_status = on_status
        self._on_disconnect = on_disconnect
        self._client: BleakClient | None = None
        self._assembler = FrameAssembler()
        self._pending: dict[str, asyncio.Future[Frame]] = {}
        # Commands the robot answers with a push instead of a reply, keyed by push name.
        self._push_waiters: dict[str, asyncio.Future[Frame]] = {}
        self._connect_lock = asyncio.Lock()
        self._expected_disconnect = False
        self.status = WinbotStatus()
        self.last_seen = 0.0

    @property
    def is_connected(self) -> bool:
        """Return True while connected."""
        return self._client is not None and self._client.is_connected

    def set_ble_device(self, ble_device: BLEDevice) -> None:
        """Update the BLEDevice (it can change when a different proxy hears it)."""
        self._ble_device = ble_device

    async def connect(self) -> None:
        """Connect and subscribe to notifications, if not already connected."""
        async with self._connect_lock:
            if self.is_connected:
                return
            self._assembler = FrameAssembler()
            try:
                client = await establish_connection(
                    BleakClientWithServiceCache,
                    self._ble_device,
                    self._ble_device.name or self._ble_device.address,
                    disconnected_callback=self._handle_disconnect,
                    ble_device_callback=lambda: self._ble_device,
                )
                await client.start_notify(NOTIFY_UUID, self._handle_notify)
            except (BleakError, TimeoutError, OSError) as err:
                raise WinbotConnectionError(str(err)) from err
            self._expected_disconnect = False
            self._client = client
            _LOGGER.debug("%s: connected", self._ble_device.address)

    async def disconnect(self) -> None:
        """Disconnect if connected."""
        async with self._connect_lock:
            client, self._client = self._client, None
            if client is None:
                return
            self._expected_disconnect = True
            try:
                await client.disconnect()
            except BleakError as err:
                _LOGGER.debug("%s: error while disconnecting: %s", self._ble_device.address, err)

    def _handle_disconnect(self, _client: BleakClient) -> None:
        expected = self._expected_disconnect
        self._client = None
        for fut in [*self._pending.values(), *self._push_waiters.values()]:
            if not fut.done():
                fut.set_exception(WinbotConnectionError("disconnected"))
        self._pending.clear()
        self._push_waiters.clear()
        _LOGGER.debug("%s: disconnected (expected=%s)", self._ble_device.address, expected)
        if not expected and self._on_disconnect:
            self._on_disconnect()

    def _handle_notify(self, _sender: Any, chunk: bytearray) -> None:
        self.last_seen = time.monotonic()
        for frame in self._assembler.feed(bytes(chunk)):
            if _LOGGER.isEnabledFor(logging.DEBUG):
                _LOGGER.debug(
                    "%s: <- %s %s %s", self._ble_device.address, frame.kind, frame.command, redact(frame.body)
                )
            if frame.kind is FrameKind.REPLY and frame.msg_id in self._pending:
                fut = self._pending.pop(frame.msg_id)
                if not fut.done():
                    fut.set_result(frame)
                continue
            if frame.kind is FrameKind.PUSH:
                self.status = apply_section(self.status, frame.command, frame.data)
                if (waiter := self._push_waiters.pop(frame.command, None)) and not waiter.done():
                    waiter.set_result(frame)
                if self._on_status:
                    self._on_status(self.status, frame)

    def _encode(self, command: str, data: dict[str, Any]) -> tuple[str, bytes]:
        msg_id = new_msg_id()
        frame_bytes = encode_request(command, data, msg_id)
        while frame_bytes[-2] == 0x0A:
            # The robot drops frames whose CRC byte equals the \n terminator
            # (tested: 3 of 3 dropped). A new message id changes the CRC.
            msg_id = new_msg_id()
            frame_bytes = encode_request(command, data, msg_id)
        return msg_id, frame_bytes

    async def _write(self, command: str, data: dict[str, Any], frame_bytes: bytes) -> None:
        assert self._client is not None
        _LOGGER.debug("%s: -> %s %s (%d bytes)", self._ble_device.address, command, data, len(frame_bytes))
        for i in range(0, len(frame_bytes), WRITE_CHUNK):
            await self._client.write_gatt_char(WRITE_UUID, frame_bytes[i : i + WRITE_CHUNK], response=False)

    async def send(self, command: str, data: dict[str, Any]) -> None:
        """Send a message the robot doesn't answer (wheelMove). Connects first if needed."""
        await self.connect()
        _msg_id, frame_bytes = self._encode(command, data)
        try:
            await self._write(command, data, frame_bytes)
        except BleakError as err:
            raise WinbotConnectionError(str(err)) from err

    async def request(self, command: str, data: dict[str, Any], *, answer_push: str | None = None) -> Frame:
        """Send a request and wait for its reply. Connects first if needed.

        answer_push: the robot answers this command with that push instead of a reply
        (clean -> onCleanInfo, in every capture).
        """
        await self.connect()
        msg_id, frame_bytes = self._encode(command, data)
        fut: asyncio.Future[Frame] = asyncio.get_running_loop().create_future()
        waiters = self._push_waiters if answer_push else self._pending
        key = answer_push or msg_id
        waiters[key] = fut
        try:
            await self._write(command, data, frame_bytes)
            _LOGGER.debug("%s: %s written", self._ble_device.address, command)
            async with asyncio.timeout(REQUEST_TIMEOUT):
                reply = await fut
        except TimeoutError as err:
            raise WinbotCommandError(f"no answer to {command}") from err
        except BleakError as err:
            raise WinbotConnectionError(str(err)) from err
        finally:
            if waiters.get(key) is fut:
                del waiters[key]
        if reply.code not in (0, None):
            raise WinbotCommandError(f"{command} failed: {reply.body}")
        return reply

    async def get_info(self) -> WinbotStatus:
        """Ask for the full status."""
        reply = await self.request("getInfo", {"timestamp": int(time.time())})
        self.status = apply_info(self.status, reply.data)
        return self.status

    async def get_stats(self) -> WinbotStats:
        """Ask for the lifetime statistics."""
        reply = await self.request("getBuryData", {})
        return parse_stats(reply.data)

    # Commands, as captured from the ECOVACS HOME app (docs/protocol.md).

    async def start(
        self,
        mode: CleanMode = CleanMode.DEPTH,
        *,
        border: bool = True,
        duration: int = 0,
        direction: str = "normal",
    ) -> None:
        """Start (or switch to) a clean. duration in minutes, 0 = until done."""
        content: dict[str, Any] = {
            "duration": duration,
            "border": int(border),
            "type": str(mode),
            "direction": direction,
        }
        if mode in (CleanMode.DEPTH, CleanMode.BORDER):
            content["windowType"] = "inner"
        await self._clean({"act": "start", "content": content})

    async def _clean(self, data: dict[str, Any]) -> None:
        await self.request("clean", data, answer_push="onCleanInfo")

    def _current_content(self) -> dict[str, Any]:
        return {
            "duration": self.status.duration or 0,
            "border": self.status.border if self.status.border is not None else 1,
            "type": self.status.router or str(CleanMode.DEPTH),
            "direction": self.status.direction or "normal",
        }

    async def pause(self) -> None:
        """Pause the current clean."""
        await self._clean({"act": "pause", "content": self._current_content()})

    async def resume(self) -> None:
        """Resume a paused clean."""
        await self._clean({"act": "resume", "content": self._current_content()})

    async def stop(self) -> None:
        """Stop the current clean."""
        await self._clean({"act": "stop", "content": {"type": self.status.router or str(CleanMode.DEPTH)}})

    async def return_home(self) -> None:
        """Send the robot back (the app's return button)."""
        await self._clean(
            {"act": "start", "content": {"type": str(CleanMode.RETURN), "border": 0, "duration": 0}}
        )

    async def spray_once(self) -> None:
        """Spray water once."""
        await self.request("sprayWater", {"direction": "auto"})

    async def spin_wheels(self, direction: str) -> None:
        """Spin the treads for wheel cleaning, about 5 s, then they stop by themselves.

        direction is "forward" or "backward" (docs/protocol.md, wheelsStart).
        """
        await self.request("wheelsStart", {"direction": direction})

    async def set_volume(self, value: int) -> None:
        """Set the voice volume."""
        reply = await self.request("setVoice", {"value": value})
        self.status = apply_section(self.status, "setVoice", reply.data or {"value": value})

    async def set_auto_spray(self, enabled: bool) -> None:
        """Turn automatic spraying on or off."""
        reply = await self.request("setSprayInfo", {"auto": int(enabled)})
        self.status = apply_section(self.status, "setSprayInfo", reply.data or {"auto": int(enabled)})

    # Remote control (docs/protocol.md, "Remote control").

    async def move(self, angle: int, speed: int = 2) -> None:
        """Send one wheelMove: the robot turns toward angle and drives, then stops by itself about a second later.

        angle is a direction on the window in degrees: 360 up, 90 right, 180 down, 270 left, and
        anything in between (45 drove diagonally up and right). speed is 1 (slow) to 3 (fast); the
        app sends 2. The robot doesn't answer wheelMove, so a bad value gives no error.
        """
        # The app sends 360 for up; 0 was never tried, so send 360 for it.
        angle = angle % 360 or 360
        await self.send("wheelMove", {"angle": angle, "speed": speed, "act": "move"})

    async def drive(self, angle: int, speed: int = 2, duration: float = 0) -> None:
        """Drive toward angle for duration seconds, repeating wheelMove like the app's joystick.

        duration 0 sends a single wheelMove, a nudge of about a second. The robot keeps going for
        about a second after the last message, then stops by itself.
        """
        loop = asyncio.get_running_loop()
        end = loop.time() + duration
        while True:
            await self.move(angle, speed)
            if loop.time() + DRIVE_INTERVAL > end:
                return
            await asyncio.sleep(DRIVE_INTERVAL)
