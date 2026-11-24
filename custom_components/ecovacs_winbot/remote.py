"""Remote control for Ecovacs Winbot: drive it around the window like the app's joystick.

The robot stops by itself about a second after the last move message (docs/protocol.md), so
a dropped connection mid-drive leaves it stopped. Each drive is capped at MAX_DRIVE_SECONDS.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterable
from typing import Any

from homeassistant.components.remote import (
    ATTR_DELAY_SECS,
    ATTR_HOLD_SECS,
    ATTR_NUM_REPEATS,
    RemoteEntity,
    RemoteEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DEFAULT_SPEED, DOMAIN, MAX_DRIVE_SECONDS, REMOTE_COMMANDS
from .coordinator import WinbotConfigEntry, WinbotCoordinator
from .entity import WinbotEntity
from .winbot import WinbotError

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: WinbotConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the remote control."""
    async_add_entities([WinbotRemote(entry.runtime_data)])


class WinbotRemote(WinbotEntity, RemoteEntity):
    """Drive the robot: up, down, left and right commands, and the drive action for any angle and speed.

    On while the robot is on. There's no power command to turn it on or off with.
    """

    def __init__(self, coordinator: WinbotCoordinator) -> None:
        """Initialize."""
        super().__init__(coordinator, RemoteEntityDescription(key="remote", translation_key="remote"))

    @property
    def available(self) -> bool:
        """Needs the robot on and HA allowed to connect."""
        return super().available and not self.coordinator.app_mode

    @property
    def is_on(self) -> bool:
        """Return True while the robot is on."""
        return self.coordinator.awake

    async def async_send_command(self, command: Iterable[str], **kwargs: Any) -> None:
        """Drive in each direction given, for hold_secs each (0 = a nudge of about a second)."""
        commands = list(command)
        if unknown := [name for name in commands if name not in REMOTE_COMMANDS]:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="unknown_command",
                translation_placeholders={"command": unknown[0], "commands": ", ".join(REMOTE_COMMANDS)},
            )
        hold = kwargs[ATTR_HOLD_SECS]
        self._check_duration(hold)
        for repeat in range(kwargs[ATTR_NUM_REPEATS]):
            for index, name in enumerate(commands):
                if repeat or index:
                    await asyncio.sleep(kwargs[ATTR_DELAY_SECS])
                await self._drive(REMOTE_COMMANDS[name], DEFAULT_SPEED, hold)

    async def async_drive(self, angle: int, speed: int, duration: float) -> None:
        """Drive toward any angle at speed 1 to 3 (the drive action; its schema limits the values)."""
        await self._drive(angle, speed, duration)

    @staticmethod
    def _check_duration(duration: float) -> None:
        # remote.send_command's hold_secs has no upper limit of its own.
        if duration > MAX_DRIVE_SECONDS:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="drive_too_long",
                translation_placeholders={"max": str(MAX_DRIVE_SECONDS)},
            )

    async def _drive(self, angle: int, speed: int, duration: float) -> None:
        try:
            await self.coordinator.async_run_command("drive", angle, speed, duration)
        except WinbotError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="command_failed",
                translation_placeholders={"error": str(err)},
            ) from err
