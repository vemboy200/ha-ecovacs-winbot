"""Buttons for Ecovacs Winbot."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DOMAIN
from .coordinator import WinbotConfigEntry
from .entity import WinbotEntity
from .winbot import WinbotError

PARALLEL_UPDATES = 1


@dataclass(frozen=True, kw_only=True)
class WinbotButtonDescription(ButtonEntityDescription):
    """Describe a Winbot button."""

    method: str
    kwargs: dict[str, Any] = field(default_factory=dict)


BUTTONS: tuple[WinbotButtonDescription, ...] = (
    WinbotButtonDescription(key="spray", translation_key="spray", method="spray_once"),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: WinbotConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up buttons."""
    coordinator = entry.runtime_data
    async_add_entities(WinbotButton(coordinator, d) for d in BUTTONS)


class WinbotButton(WinbotEntity, ButtonEntity):
    """A Winbot command button."""

    entity_description: WinbotButtonDescription

    @property
    def available(self) -> bool:
        """Buttons need the robot on and HA allowed to connect."""
        return super().available and not self.coordinator.app_mode

    async def async_press(self) -> None:
        """Send the command."""
        try:
            await self.coordinator.async_run_command(
                self.entity_description.method, **self.entity_description.kwargs
            )
        except WinbotError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="command_failed",
                translation_placeholders={"error": str(err)},
            ) from err
