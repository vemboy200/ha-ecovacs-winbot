"""The Ecovacs Winbot integration."""

from __future__ import annotations

import voluptuous as vol

from homeassistant.components.remote import DOMAIN as REMOTE_DOMAIN
from homeassistant.const import CONF_ADDRESS, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv, entity_registry as er, service
from homeassistant.helpers.typing import ConfigType

from .const import DEFAULT_SPEED, DOMAIN, MAX_DRIVE_SECONDS, WinbotService, WinbotServiceArgument
from .coordinator import WinbotConfigEntry, WinbotCoordinator

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

DRIVE_SCHEMA = cv.make_entity_service_schema(
    {
        vol.Required(WinbotServiceArgument.ANGLE): vol.All(vol.Coerce(int), vol.Range(min=0, max=360)),
        vol.Optional(WinbotServiceArgument.SPEED, default=DEFAULT_SPEED): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=3)
        ),
        vol.Optional(WinbotServiceArgument.DURATION, default=1): vol.All(
            vol.Coerce(float), vol.Range(min=0, max=MAX_DRIVE_SECONDS)
        ),
    }
)

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
    Platform.NUMBER,
    Platform.REMOTE,
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.VACUUM,
]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the drive action."""
    service.async_register_platform_entity_service(
        hass,
        DOMAIN,
        WinbotService.DRIVE,
        entity_domain=REMOTE_DOMAIN,
        schema=DRIVE_SCHEMA,
        func="async_drive",
    )
    return True


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
