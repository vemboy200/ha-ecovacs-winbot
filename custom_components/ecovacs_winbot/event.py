"""Event entities for Ecovacs Winbot: cleaning (started / done / interrupted / error / out of water) and bumper."""

from __future__ import annotations

from homeassistant.components.event import EventEntity, EventEntityDescription
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import (
    EVENT_BUMPED,
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
    """Set up the event entities."""
    coordinator = entry.runtime_data
    async_add_entities([WinbotCleaningEvent(coordinator), WinbotBumperEvent(coordinator)])


class WinbotEvent(WinbotEntity, EventEntity):
    """Fires the coordinator's events that are among this entity's event types."""

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


class WinbotCleaningEvent(WinbotEvent):
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


class WinbotBumperEvent(WinbotEvent):
    """Fires when the robot reports a bump.

    Disabled by default: the robot reports the same code for every edge and both bumpers,
    and repeats it about once a second while pressed against the frame, so it's rarely
    useful in automations.
    """

    def __init__(self, coordinator: WinbotCoordinator) -> None:
        """Initialize."""
        super().__init__(
            coordinator,
            EventEntityDescription(
                key="bumper",
                translation_key="bumper",
                event_types=[EVENT_BUMPED],
                entity_registry_enabled_default=False,
            ),
        )
