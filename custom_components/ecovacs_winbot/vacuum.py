"""Vacuum entity for Ecovacs Winbot.

It really is a vacuum: suction is what holds it on the glass.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.vacuum import (
    StateVacuumEntity,
    StateVacuumEntityDescription,
    VacuumActivity,
    VacuumEntityFeature,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DOMAIN
from .coordinator import WinbotConfigEntry, WinbotCoordinator
from .entity import WinbotEntity
from .winbot import Activity, CleanMode, WinbotError

PARALLEL_UPDATES = 1

ACTIVITY_MAP = {
    Activity.IDLE: VacuumActivity.IDLE,
    Activity.CLEANING: VacuumActivity.CLEANING,
    Activity.PAUSED: VacuumActivity.PAUSED,
    Activity.RETURNING: VacuumActivity.RETURNING,
    Activity.REMOTE_CONTROL: VacuumActivity.CLEANING,
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: WinbotConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the vacuum entity."""
    async_add_entities([WinbotVacuum(entry.runtime_data)])


class WinbotVacuum(WinbotEntity, StateVacuumEntity):
    """The Winbot as a vacuum: start, pause, stop, return, spot clean."""

    _attr_name = None
    _attr_supported_features = (
        VacuumEntityFeature.STATE
        | VacuumEntityFeature.START
        | VacuumEntityFeature.PAUSE
        | VacuumEntityFeature.STOP
        | VacuumEntityFeature.RETURN_HOME
        | VacuumEntityFeature.CLEAN_SPOT
    )

    def __init__(self, coordinator: WinbotCoordinator) -> None:
        """Initialize."""
        super().__init__(coordinator, StateVacuumEntityDescription(key="vacuum"))

    @property
    def available(self) -> bool:
        """Needs the robot on and HA allowed to connect."""
        return super().available and not self.coordinator.app_mode

    @property
    def activity(self) -> VacuumActivity | None:
        """Return what the robot is doing."""
        data = self.coordinator.data
        if any(data.error_codes):
            return VacuumActivity.ERROR
        return ACTIVITY_MAP.get(data.activity) if data.activity else None

    async def _run(self, method: str, **kwargs: Any) -> None:
        try:
            await self.coordinator.async_run_command(method, **kwargs)
        except WinbotError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="command_failed",
                translation_placeholders={"error": str(err)},
            ) from err

    async def async_start(self) -> None:
        """Start a deep clean, or resume if paused."""
        if self.coordinator.data.activity is Activity.PAUSED:
            await self._run("resume")
        else:
            await self._run("start", mode=CleanMode.DEPTH)

    async def async_pause(self) -> None:
        """Pause."""
        await self._run("pause")

    async def async_stop(self, **kwargs: Any) -> None:
        """Stop."""
        await self._run("stop")

    async def async_return_to_base(self, **kwargs: Any) -> None:
        """Return (the app's return button)."""
        await self._run("return_home")

    async def async_clean_spot(self, **kwargs: Any) -> None:
        """Spot clean."""
        await self._run("start", mode=CleanMode.SPOT, border=False)
