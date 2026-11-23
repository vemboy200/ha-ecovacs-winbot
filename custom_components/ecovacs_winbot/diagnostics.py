"""Diagnostics for Ecovacs Winbot."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import HomeAssistant

from .coordinator import WinbotConfigEntry
from .winbot import redact
from .winbot.products import model_name

TO_REDACT = {CONF_ADDRESS, "serial_number"}


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: WinbotConfigEntry) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = entry.runtime_data
    status = asdict(coordinator.data)
    # Raw getRobotInfo, with every version the robot reports (SVER firmware, BVER, VVER, MID).
    robot_info = status.pop("robot_info")
    return {
        "entry_data": async_redact_data(dict(entry.data), TO_REDACT),
        "model": {"model_id": coordinator.model_id, "name": model_name(coordinator.model_id)},
        "connection": {
            "awake": coordinator.awake,
            "connected": bool(coordinator.client and coordinator.client.is_connected),
            "released": coordinator.released,
            "app_mode": coordinator.app_mode,
            "rssi": coordinator.rssi,
        },
        "robot_info": redact(robot_info),
        "status": async_redact_data(redact(status), TO_REDACT),
    }
