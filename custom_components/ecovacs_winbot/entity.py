"""Base entity for Ecovacs Winbot."""

from __future__ import annotations

from homeassistant.helpers.device_registry import CONNECTION_BLUETOOTH, DeviceInfo
from homeassistant.helpers.entity import EntityDescription
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import WinbotCoordinator


class WinbotEntity(CoordinatorEntity[WinbotCoordinator]):
    """A Winbot entity. Unavailable while the robot is off, unless it says otherwise."""

    _attr_has_entity_name = True
    available_when_off = False

    def __init__(self, coordinator: WinbotCoordinator, description: EntityDescription) -> None:
        """Initialize."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.address}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.address)},
            connections={(CONNECTION_BLUETOOTH, coordinator.address)},
            manufacturer="Ecovacs",
            model="Winbot",
            name=coordinator.config_entry.title,
        )

    @property
    def available(self) -> bool:
        """Return availability."""
        if self.available_when_off:
            return True
        return super().available and self.coordinator.awake and self.coordinator.data.state is not None
