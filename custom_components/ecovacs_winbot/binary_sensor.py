"""Binary sensors for Ecovacs Winbot."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import WinbotConfigEntry
from .entity import WinbotEntity
from .winbot import WinbotStatus

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class WinbotBinarySensorDescription(BinarySensorEntityDescription):
    """Describe a Winbot binary sensor."""

    value_fn: Callable[[WinbotStatus], bool | None]


BINARY_SENSORS: tuple[WinbotBinarySensorDescription, ...] = (
    WinbotBinarySensorDescription(
        key="charging",
        device_class=BinarySensorDeviceClass.BATTERY_CHARGING,
        value_fn=lambda s: s.charging,
    ),
    WinbotBinarySensorDescription(
        key="attached",
        translation_key="attached",
        value_fn=lambda s: s.attached,
    ),
    WinbotBinarySensorDescription(
        key="out_of_water",
        translation_key="out_of_water",
        device_class=BinarySensorDeviceClass.PROBLEM,
        value_fn=lambda s: s.out_of_water,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: WinbotConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up binary sensors."""
    coordinator = entry.runtime_data
    async_add_entities(WinbotBinarySensor(coordinator, d) for d in BINARY_SENSORS)


class WinbotBinarySensor(WinbotEntity, BinarySensorEntity):
    """A Winbot binary sensor."""

    entity_description: WinbotBinarySensorDescription

    @property
    def is_on(self) -> bool | None:
        """Return the state."""
        return self.entity_description.value_fn(self.coordinator.data)
