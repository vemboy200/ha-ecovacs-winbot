"""The Ecovacs Winbot integration."""

from __future__ import annotations

from homeassistant.const import CONF_ADDRESS, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .coordinator import WinbotConfigEntry, WinbotCoordinator

# Entity keys from earlier versions: buttons that moved into the vacuum entity,
# and binary sensors that duplicated the battery and charging entities.
RETIRED_KEYS = {
    "start",
    "start_border",
    "start_spot",
    "start_timed",
    "pause",
    "resume",
    "stop",
    "return",
    "battery_low",
    "plugged_in",
}

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.EVENT,
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.VACUUM,
]


async def async_setup_entry(hass: HomeAssistant, entry: WinbotConfigEntry) -> bool:
    """Set up a Winbot from a config entry.

    No connection is needed here: the robot is often switched off, which just
    shows as "Off" until it starts advertising again.
    """
    coordinator = WinbotCoordinator(hass, entry, entry.data[CONF_ADDRESS])
    registry = er.async_get(hass)
    retired = {f"{coordinator.address}_{key}" for key in RETIRED_KEYS}
    for reg_entry in er.async_entries_for_config_entry(registry, entry.entry_id):
        if reg_entry.unique_id in retired:
            registry.async_remove(reg_entry.entity_id)
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    coordinator.async_start()
    entry.async_on_unload(coordinator.async_shutdown)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: WinbotConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
