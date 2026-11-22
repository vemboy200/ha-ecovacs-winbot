"""Binary sensors for Ecovacs Winbot."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import STATE_OFF, STATE_ON
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .coordinator import WinbotConfigEntry
from .entity import WinbotEntity
from .winbot import WinbotStatus

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class WinbotBinarySensorDescription(BinarySensorEntityDescription):
    """Describe a Winbot binary sensor."""

    value_fn: Callable[[WinbotStatus], bool | None]
    # Keep the last value across restarts, for data the robot only pushes.
    restore: bool = False


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
        # Only known from onSprayInfo pushes during a clean; getInfo doesn't report it.
        restore=True,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: WinbotConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up binary sensors."""
    coordinator = entry.runtime_data
    async_add_entities(
        (WinbotRestoreBinarySensor if d.restore else WinbotBinarySensor)(coordinator, d)
        for d in BINARY_SENSORS
    )


class WinbotBinarySensor(WinbotEntity, BinarySensorEntity):
    """A Winbot binary sensor."""

    entity_description: WinbotBinarySensorDescription

    @property
    def is_on(self) -> bool | None:
        """Return the state."""
        return self.entity_description.value_fn(self.coordinator.data)


class WinbotRestoreBinarySensor(WinbotBinarySensor, RestoreEntity):
    """A binary sensor that shows its last value until the robot reports a new one."""

    _restored: bool | None = None

    async def async_added_to_hass(self) -> None:
        """Restore the last value."""
        await super().async_added_to_hass()
        if (last := await self.async_get_last_state()) and last.state in (STATE_ON, STATE_OFF):
            self._restored = last.state == STATE_ON

    @property
    def is_on(self) -> bool | None:
        """Return the reported value, or the restored one until there is one."""
        value = super().is_on
        return self._restored if value is None else value
