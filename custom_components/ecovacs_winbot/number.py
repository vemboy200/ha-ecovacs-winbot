"""Number entities for Ecovacs Winbot."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberEntityDescription, NumberMode
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
    """Set up number entities."""
    async_add_entities([WinbotVolume(entry.runtime_data)])


class WinbotVolume(WinbotEntity, NumberEntity):
    """Voice volume.

    The app's slider sends steps of 7; the robot accepts 0-63 and clamps
    anything higher to 63 (tested with a 0-100 sweep).
    """

    _attr_native_min_value = 0
    _attr_native_max_value = 63
    _attr_native_step = 1
    _attr_mode = NumberMode.SLIDER

    def __init__(self, coordinator: WinbotCoordinator) -> None:
        """Initialize."""
        super().__init__(
            coordinator,
            NumberEntityDescription(
                key="volume", translation_key="volume", entity_category=EntityCategory.CONFIG
            ),
        )

    @property
    def available(self) -> bool:
        """Needs the robot on and HA allowed to connect."""
        return super().available and not self.coordinator.app_mode

    @property
    def native_value(self) -> float | None:
        """Return the volume."""
        return self.coordinator.data.volume

    async def async_set_native_value(self, value: float) -> None:
        """Set the volume."""
        try:
            await self.coordinator.async_run_command("set_volume", int(value))
        except WinbotError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="command_failed",
                translation_placeholders={"error": str(err)},
            ) from err
