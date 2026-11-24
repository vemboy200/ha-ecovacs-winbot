"""Sensors for Ecovacs Winbot."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, SIGNAL_STRENGTH_DECIBELS_MILLIWATT, EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import TRIGGERS
from .coordinator import WinbotConfigEntry, WinbotCoordinator
from .entity import WinbotEntity
from .winbot import Activity, WinbotStats, WinbotStatus

PARALLEL_UPDATES = 0

STATE_OFF = "off"
CLEAN_MODES = ["depth", "auto", "border", "spot", "return", "control"]
# The robot's trigger values, as state keys (which have to be lowercase).
TRIGGER_STATES = {trigger: trigger.replace("workComplete", "work_complete") for trigger in TRIGGERS}


@dataclass(frozen=True, kw_only=True)
class WinbotSensorDescription(SensorEntityDescription):
    """Describe a Winbot sensor."""

    value_fn: Callable[[WinbotStatus], str | int | None]


SENSORS: tuple[WinbotSensorDescription, ...] = (
    WinbotSensorDescription(
        key="battery",
        device_class=SensorDeviceClass.BATTERY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda s: s.battery_percent,
    ),
    WinbotSensorDescription(
        key="clean_mode",
        translation_key="clean_mode",
        device_class=SensorDeviceClass.ENUM,
        options=CLEAN_MODES,
        value_fn=lambda s: s.router if s.router in CLEAN_MODES else None,
    ),
    WinbotSensorDescription(
        key="last_trigger",
        translation_key="last_trigger",
        device_class=SensorDeviceClass.ENUM,
        options=list(TRIGGER_STATES.values()),
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda s: TRIGGER_STATES.get(s.trigger) if s.trigger else None,
    ),
    WinbotSensorDescription(
        key="error",
        translation_key="error",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: ",".join(str(c) for c in s.error_codes) if s.error_codes else None,
    ),
)


@dataclass(frozen=True, kw_only=True)
class WinbotStatsSensorDescription(SensorEntityDescription):
    """Describe a lifetime statistics sensor."""

    value_fn: Callable[[WinbotStats], int | None]


STATS_SENSORS: tuple[WinbotStatsSensorDescription, ...] = (
    WinbotStatsSensorDescription(
        key="charge_count",
        translation_key="charge_count",
        entity_category=EntityCategory.DIAGNOSTIC,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda s: s.charge_count,
    ),
    WinbotStatsSensorDescription(
        key="no_water_count",
        translation_key="no_water_count",
        entity_category=EntityCategory.DIAGNOSTIC,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda s: s.no_water_count,
    ),
    WinbotStatsSensorDescription(
        key="fall_count",
        translation_key="fall_count",
        entity_category=EntityCategory.DIAGNOSTIC,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda s: s.fall_count,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: WinbotConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up sensors."""
    coordinator = entry.runtime_data
    async_add_entities(
        [
            WinbotStatusSensor(coordinator),
            WinbotSignalSensor(coordinator),
            *(WinbotSensor(coordinator, d) for d in SENSORS),
            *(WinbotStatsSensor(coordinator, d) for d in STATS_SENSORS),
        ]
    )


class WinbotSensor(WinbotEntity, SensorEntity):
    """A Winbot sensor."""

    entity_description: WinbotSensorDescription

    @property
    def native_value(self) -> str | int | None:
        """Return the value."""
        return self.entity_description.value_fn(self.coordinator.data)


class WinbotStatsSensor(WinbotEntity, SensorEntity):
    """A lifetime counter from the robot's statistics."""

    entity_description: WinbotStatsSensorDescription

    @property
    def native_value(self) -> int | None:
        """Return the count."""
        return self.entity_description.value_fn(self.coordinator.stats)


class WinbotStatusSensor(WinbotEntity, SensorEntity):
    """What the robot is doing, including Off when it isn't advertising."""

    available_when_off = True

    def __init__(self, coordinator: WinbotCoordinator) -> None:
        """Initialize."""
        super().__init__(
            coordinator,
            SensorEntityDescription(
                key="status",
                translation_key="status",
                device_class=SensorDeviceClass.ENUM,
                options=[STATE_OFF, *(a.value for a in Activity)],
            ),
        )

    @property
    def native_value(self) -> str | None:
        """Return the status."""
        if not self.coordinator.awake:
            return STATE_OFF
        activity = self.coordinator.data.activity
        return activity.value if activity else None

    @property
    def extra_state_attributes(self) -> dict[str, str | None]:
        """Expose the raw values while the protocol is still being learned."""
        data = self.coordinator.data
        return {
            "raw_state": data.state,
            "last_trigger": data.trigger,
            "motion_state": data.motion_state,
            "connected": str(self.coordinator.connected),
        }


class WinbotSignalSensor(WinbotEntity, SensorEntity):
    """Bluetooth signal strength, from the robot's advertisements as heard by the best adapter or proxy."""

    def __init__(self, coordinator: WinbotCoordinator) -> None:
        """Initialize."""
        super().__init__(
            coordinator,
            SensorEntityDescription(
                key="rssi",
                device_class=SensorDeviceClass.SIGNAL_STRENGTH,
                native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
                state_class=SensorStateClass.MEASUREMENT,
                entity_category=EntityCategory.DIAGNOSTIC,
            ),
        )

    @property
    def available(self) -> bool:
        """Only while the robot is advertising (a stale reading would be misleading)."""
        return self.coordinator.awake and self.coordinator.rssi is not None

    @property
    def native_value(self) -> int | None:
        """Return the RSSI in dBm."""
        return self.coordinator.rssi
