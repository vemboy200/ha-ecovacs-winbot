"""Buttons for Ecovacs Winbot."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.const import EntityCategory
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
    # Only possible while the robot is attached to the glass; unavailable otherwise, as the app hides it.
    needs_glass: bool = False
    # Only offered while the robot is off the glass: spinning the treads there would drive it.
    needs_off_glass: bool = False


BUTTONS: tuple[WinbotButtonDescription, ...] = (
    WinbotButtonDescription(key="spray", translation_key="spray", method="spray_once", needs_glass=True),
    WinbotButtonDescription(
        key="wheels_forward",
        translation_key="wheels_forward",
        method="spin_wheels",
        kwargs={"direction": "forward"},
        needs_off_glass=True,
        entity_category=EntityCategory.CONFIG,
    ),
    WinbotButtonDescription(
        key="wheels_backward",
        translation_key="wheels_backward",
        method="spin_wheels",
        kwargs={"direction": "backward"},
        needs_off_glass=True,
        entity_category=EntityCategory.CONFIG,
    ),
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
        """Buttons need the robot on, HA allowed to connect, and some the robot on (or off) the glass."""
        attached = self.coordinator.data.attached
        return (
            super().available
            and not self.coordinator.paused
            and not (self.entity_description.needs_glass and attached is False)
            and not (self.entity_description.needs_off_glass and attached is not False)
        )

    async def async_press(self) -> None:
        """Send the command."""
        try:
            await self.coordinator.async_run_command(
                self.entity_description.method,
                needs_glass=self.entity_description.needs_glass,
                **self.entity_description.kwargs,
            )
        except WinbotError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="command_failed",
                translation_placeholders={"error": str(err)},
            ) from err
