"""Switches for Ecovacs Winbot."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DOMAIN
from .coordinator import WinbotConfigEntry, WinbotCoordinator
from .entity import WinbotEntity
from .winbot import WinbotError

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: WinbotConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up switches."""
    coordinator = entry.runtime_data
    async_add_entities([WinbotAutoSpraySwitch(coordinator), WinbotAppModeSwitch(coordinator)])


class WinbotAutoSpraySwitch(WinbotEntity, SwitchEntity):
    """Automatic spraying."""

    def __init__(self, coordinator: WinbotCoordinator) -> None:
        """Initialize."""
        super().__init__(
            coordinator,
            SwitchEntityDescription(
                key="auto_spray", translation_key="auto_spray", entity_category=EntityCategory.CONFIG
            ),
        )

    @property
    def available(self) -> bool:
        """Needs the robot on and HA allowed to connect."""
        return super().available and not self.coordinator.app_mode

    @property
    def is_on(self) -> bool | None:
        """Return the state."""
        return self.coordinator.data.auto_spray

    async def _set(self, enabled: bool) -> None:
        try:
            await self.coordinator.async_run_command("set_auto_spray", enabled)
        except WinbotError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="command_failed",
                translation_placeholders={"error": str(err)},
            ) from err

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn automatic spraying on."""
        await self._set(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn automatic spraying off."""
        await self._set(False)


class WinbotAppModeSwitch(WinbotEntity, SwitchEntity):
    """When on, HA lets go of the robot so the ECOVACS HOME app can connect."""

    available_when_off = True

    def __init__(self, coordinator: WinbotCoordinator) -> None:
        """Initialize."""
        super().__init__(
            coordinator,
            SwitchEntityDescription(
                key="app_mode", translation_key="app_mode", entity_category=EntityCategory.CONFIG
            ),
        )

    @property
    def is_on(self) -> bool:
        """Return the state."""
        return self.coordinator.app_mode

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Let the app connect."""
        await self.coordinator.async_set_app_mode(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Let HA connect again."""
        await self.coordinator.async_set_app_mode(False)
