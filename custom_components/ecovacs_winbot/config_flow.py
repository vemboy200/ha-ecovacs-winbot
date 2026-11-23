"""Config flow for Ecovacs Winbot."""

from __future__ import annotations

import logging
from typing import Any

import probatio

from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
    async_ble_device_from_address,
    async_discovered_service_info,
)
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_ADDRESS

from .const import DOMAIN
from .winbot import WinbotClient, WinbotError

_LOGGER = logging.getLogger(__name__)

WINBOT_MANUFACTURER_ID = 30337
WINBOT_SERVICE_UUID = "0000fff0-0000-1000-8000-00805f9b34fb"


def _is_winbot(info: BluetoothServiceInfoBleak) -> bool:
    if (info.name or "").startswith("WINBOT_"):
        return True
    return WINBOT_MANUFACTURER_ID in info.manufacturer_data and WINBOT_SERVICE_UUID in info.service_uuids


def _title(info: BluetoothServiceInfoBleak) -> str:
    return f"Winbot {info.address.replace(':', '')[-4:]}"


async def _async_test_connection(flow: ConfigFlow, address: str) -> str | None:
    """Connect to the robot and read its status. Return an error key, or None if it worked."""
    if (ble_device := async_ble_device_from_address(flow.hass, address, connectable=True)) is None:
        return "cannot_connect"
    client = WinbotClient(ble_device)
    try:
        await client.get_info()
    except WinbotError:
        return "cannot_connect"
    except Exception:
        _LOGGER.exception("Unexpected error while connecting to %s", address)
        return "unknown"
    finally:
        await client.disconnect()
    return None


class WinbotConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Ecovacs Winbot."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the flow."""
        self._discovery: BluetoothServiceInfoBleak | None = None
        self._discovered: dict[str, BluetoothServiceInfoBleak] = {}

    async def async_step_bluetooth(self, discovery_info: BluetoothServiceInfoBleak) -> ConfigFlowResult:
        """Handle a robot found by Bluetooth discovery."""
        await self.async_set_unique_id(discovery_info.address)
        self._abort_if_unique_id_configured()
        if not _is_winbot(discovery_info):
            return self.async_abort(reason="not_supported")
        self._discovery = discovery_info
        self.context["title_placeholders"] = {"name": _title(discovery_info)}
        return await self.async_step_bluetooth_confirm()

    async def async_step_bluetooth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm a discovered robot."""
        assert self._discovery is not None
        errors: dict[str, str] = {}
        if user_input is not None:
            if not (error := await _async_test_connection(self, self._discovery.address)):
                return self.async_create_entry(
                    title=_title(self._discovery), data={CONF_ADDRESS: self._discovery.address}
                )
            errors["base"] = error
        self._set_confirm_only()
        return self.async_show_form(
            step_id="bluetooth_confirm",
            description_placeholders={"name": _title(self._discovery)},
            errors=errors,
        )

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Pick a robot from the ones Home Assistant can currently hear."""
        errors: dict[str, str] = {}
        if user_input is not None:
            address = user_input[CONF_ADDRESS]
            await self.async_set_unique_id(address, raise_on_progress=False)
            self._abort_if_unique_id_configured()
            if not (error := await _async_test_connection(self, address)):
                return self.async_create_entry(
                    title=_title(self._discovered[address]), data={CONF_ADDRESS: address}
                )
            errors["base"] = error

        current = self._async_current_ids(include_ignore=False)
        for info in async_discovered_service_info(self.hass, connectable=True):
            if info.address not in current and _is_winbot(info):
                self._discovered[info.address] = info
        if not self._discovered:
            return self.async_abort(reason="no_devices_found")
        return self.async_show_form(
            step_id="user",
            data_schema=probatio.Schema(
                {
                    probatio.Required(CONF_ADDRESS): probatio.In(
                        {addr: f"{_title(info)} ({addr})" for addr, info in self._discovered.items()}
                    )
                }
            ),
            errors=errors,
        )
