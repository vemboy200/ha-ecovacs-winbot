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

from .models import CleanMode, WinbotStatus, apply_info, apply_section
from .protocol import Frame, FrameAssembler, FrameKind, encode_request, new_msg_id

_LOGGER = logging.getLogger(__name__)

NOTIFY_UUID = "0000fff1-0000-1000-8000-00805f9b34fb"
WRITE_UUID = "0000fff2-0000-1000-8000-00805f9b34fb"
REQUEST_TIMEOUT = 8.0
WRITE_CHUNK = 180  # stays under any negotiated MTU we've seen


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
        for fut in self._pending.values():
            if not fut.done():
                fut.set_exception(WinbotConnectionError("disconnected"))
        self._pending.clear()
        _LOGGER.debug("%s: disconnected (expected=%s)", self._ble_device.address, expected)
        if not expected and self._on_disconnect:
            self._on_disconnect()

    def _handle_notify(self, _sender: Any, chunk: bytearray) -> None:
        self.last_seen = time.monotonic()
        for frame in self._assembler.feed(bytes(chunk)):
            _LOGGER.debug("%s: <- %s %s %s", self._ble_device.address, frame.kind, frame.command, frame.body)
            if frame.kind is FrameKind.REPLY and frame.msg_id in self._pending:
                fut = self._pending.pop(frame.msg_id)
                if not fut.done():
                    fut.set_result(frame)
                continue
            if frame.kind is FrameKind.PUSH:
                self.status = apply_section(self.status, frame.command, frame.data)
                if self._on_status:
                    self._on_status(self.status, frame)

    async def request(self, command: str, data: dict[str, Any]) -> Frame:
        """Send a request and wait for its reply. Connects first if needed."""
        await self.connect()
        assert self._client is not None
        msg_id = new_msg_id()
        frame_bytes = encode_request(command, data, msg_id)
        fut: asyncio.Future[Frame] = asyncio.get_running_loop().create_future()
        self._pending[msg_id] = fut
        _LOGGER.debug("%s: -> %s %s", self._ble_device.address, command, data)
        try:
            for i in range(0, len(frame_bytes), WRITE_CHUNK):
                await self._client.write_gatt_char(
                    WRITE_UUID, frame_bytes[i : i + WRITE_CHUNK], response=False
                )
            async with asyncio.timeout(REQUEST_TIMEOUT):
                reply = await fut
        except TimeoutError as err:
            raise WinbotCommandError(f"no reply to {command}") from err
        except BleakError as err:
            raise WinbotConnectionError(str(err)) from err
        finally:
            self._pending.pop(msg_id, None)
        if reply.code not in (0, None):
            raise WinbotCommandError(f"{command} failed: {reply.body}")
        return reply

    async def get_info(self) -> WinbotStatus:
        """Ask for the full status."""
        reply = await self.request("getInfo", {"timestamp": int(time.time())})
        self.status = apply_info(self.status, reply.data)
        return self.status

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
        await self.request("clean", {"act": "start", "content": content})

    def _current_content(self) -> dict[str, Any]:
        return {
            "duration": self.status.duration or 0,
            "border": self.status.border if self.status.border is not None else 1,
            "type": self.status.router or str(CleanMode.DEPTH),
            "direction": self.status.direction or "normal",
        }

    async def pause(self) -> None:
        """Pause the current clean."""
        await self.request("clean", {"act": "pause", "content": self._current_content()})

    async def resume(self) -> None:
        """Resume a paused clean."""
        await self.request("clean", {"act": "resume", "content": self._current_content()})

    async def stop(self) -> None:
        """Stop the current clean."""
        await self.request(
            "clean", {"act": "stop", "content": {"type": self.status.router or str(CleanMode.DEPTH)}}
        )

    async def return_home(self) -> None:
        """Send the robot back (the app's return button)."""
        await self.request(
            "clean", {"act": "start", "content": {"type": str(CleanMode.RETURN), "border": 0, "duration": 0}}
        )

    async def spray_once(self) -> None:
        """Spray water once."""
        await self.request("sprayWater", {"direction": "auto"})

    async def set_auto_spray(self, enabled: bool) -> None:
        """Turn automatic spraying on or off."""
        reply = await self.request("setSprayInfo", {"auto": int(enabled)})
        self.status = apply_section(self.status, "setSprayInfo", reply.data or {"auto": int(enabled)})
