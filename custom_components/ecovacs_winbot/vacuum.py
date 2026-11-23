"""Vacuum entity for Ecovacs Winbot.

It really is a vacuum: suction is what holds it on the glass.

Cleaning modes are exposed as fan speeds (like Roborock does for its modes):
pick one, then Start uses it; picking one mid-clean switches right away.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.vacuum import (
    StateVacuumEntity,
    StateVacuumEntityDescription,
    VacuumActivity,
    VacuumEntityFeature,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DOMAIN
from .coordinator import WinbotConfigEntry, WinbotCoordinator
from .entity import WinbotEntity
from .winbot import Activity, CleanMode, WinbotError, WinbotStatus

PARALLEL_UPDATES = 1

ACTIVITY_MAP = {
    Activity.IDLE: VacuumActivity.IDLE,
    Activity.CLEANING: VacuumActivity.CLEANING,
    Activity.PAUSED: VacuumActivity.PAUSED,
    Activity.RETURNING: VacuumActivity.RETURNING,
    Activity.REMOTE_CONTROL: VacuumActivity.CLEANING,
}


@dataclass(frozen=True)
class Mode:
    """A cleaning mode as the app sends it."""

    mode: CleanMode
    border: bool
    duration: int = 0


# Values match what the app sent (docs/protocol.md). duration is in minutes;
# 5 and 10 were both confirmed on the robot.
MODES: dict[str, Mode] = {
    "Deep": Mode(CleanMode.DEPTH, border=True),
    "Edge": Mode(CleanMode.BORDER, border=False),
    "Spot": Mode(CleanMode.SPOT, border=False),
    "5 minutes": Mode(CleanMode.DEPTH, border=True, duration=5),
    "10 minutes": Mode(CleanMode.DEPTH, border=True, duration=10),
}
DEFAULT_MODE = "Deep"
# The mode name for each cleaning mode the robot reports.
MODE_NAMES: dict[str, str] = {CleanMode.DEPTH: "Deep", CleanMode.BORDER: "Edge", CleanMode.SPOT: "Spot"}


def _mode_from_status(status: WinbotStatus) -> str | None:
    """Name of the mode the robot reports, if it's one of ours."""
    if status.router == CleanMode.DEPTH and status.duration in (5, 10):
        return f"{status.duration} minutes"
    return MODE_NAMES.get(status.router) if status.router else None


async def async_setup_entry(
    hass: HomeAssistant,
    entry: WinbotConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the vacuum entity."""
    async_add_entities([WinbotVacuum(entry.runtime_data)])


class WinbotVacuum(WinbotEntity, StateVacuumEntity):
    """The Winbot as a vacuum: start, pause, stop, return, spot clean, cleaning mode."""

    _attr_name = None
    _attr_supported_features = (
        VacuumEntityFeature.STATE
        | VacuumEntityFeature.START
        | VacuumEntityFeature.PAUSE
        | VacuumEntityFeature.STOP
        | VacuumEntityFeature.RETURN_HOME
        | VacuumEntityFeature.CLEAN_SPOT
        | VacuumEntityFeature.FAN_SPEED
    )

    def __init__(self, coordinator: WinbotCoordinator) -> None:
        """Initialize."""
        super().__init__(coordinator, StateVacuumEntityDescription(key="vacuum"))
        self._attr_fan_speed_list = list(MODES)
        self._selected = DEFAULT_MODE

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

    @property
    def fan_speed(self) -> str | None:
        """Mode in use while cleaning; otherwise the mode Start will use."""
        if self.coordinator.data.is_active and (current := _mode_from_status(self.coordinator.data)):
            return current
        return self._selected

    async def _run(self, method: str, **kwargs: Any) -> None:
        try:
            await self.coordinator.async_run_command(method, **kwargs)
        except WinbotError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="command_failed",
                translation_placeholders={"error": str(err)},
            ) from err

    async def _start(self, name: str) -> None:
        mode = MODES[name]
        await self._run("start", mode=mode.mode, border=mode.border, duration=mode.duration)

    async def async_start(self) -> None:
        """Start a clean in the selected mode, or resume if paused."""
        if self.coordinator.data.activity is Activity.PAUSED:
            await self._run("resume")
        else:
            await self._start(self._selected)

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
        await self._start("Spot")

    async def async_set_fan_speed(self, fan_speed: str, **kwargs: Any) -> None:
        """Pick the cleaning mode; switches immediately if already cleaning."""
        if fan_speed not in MODES:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="unknown_mode",
                translation_placeholders={"mode": fan_speed, "modes": ", ".join(MODES)},
            )
        self._selected = fan_speed
        if self.coordinator.data.activity in (Activity.CLEANING, Activity.PAUSED):
            await self._start(fan_speed)
        else:
            self.async_write_ha_state()
