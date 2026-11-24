"""Event entity for Ecovacs Winbot (started / done cleaning / done returning / interrupted / error / out of water)."""

from __future__ import annotations

from homeassistant.components.event import EventEntity, EventEntityDescription
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import (
    EVENT_ERROR,
    EVENT_FINISHED,
    EVENT_INTERRUPTED,
    EVENT_OUT_OF_WATER,
    EVENT_RETURNED,
    EVENT_STARTED,
)
from .coordinator import WinbotConfigEntry, WinbotCoordinator
from .entity import WinbotEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: WinbotConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the event entity."""
    async_add_entities([WinbotCleaningEvent(entry.runtime_data)])


class WinbotCleaningEvent(WinbotEntity, EventEntity):
    """Fires when a clean starts, finishes on its own, a return finishes, a clean is interrupted (robot went off mid-clean), the robot reports an error (it stops when that happens), or it runs out of water."""

    available_when_off = True

    def __init__(self, coordinator: WinbotCoordinator) -> None:
        """Initialize."""
        super().__init__(
            coordinator,
            EventEntityDescription(
                key="cleaning",
                translation_key="cleaning",
                event_types=[
                    EVENT_STARTED,
                    EVENT_FINISHED,
                    EVENT_RETURNED,
                    EVENT_INTERRUPTED,
                    EVENT_ERROR,
                    EVENT_OUT_OF_WATER,
                ],
            ),
        )

    async def async_added_to_hass(self) -> None:
        """Subscribe to robot events."""
        await super().async_added_to_hass()
        self.async_on_remove(self.coordinator.async_add_event_listener(self._handle_event))

    @callback
    def _handle_event(self, event_type: str, attributes: dict[str, object] | None = None) -> None:
        if event_type not in self.event_types:
            return
        self._trigger_event(event_type, attributes)
        self.async_write_ha_state()
