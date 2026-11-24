"""Winbot status model, filled from getInfo replies and on* pushes."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import StrEnum
from typing import Any


class CleanMode(StrEnum):
    """Values of `type` in a clean/start command (and of cleanState.router)."""

    DEPTH = "depth"
    BORDER = "border"
    SPOT = "spot"
    RETURN = "return"


class Activity(StrEnum):
    """Simplified activity derived from state + motionState + router."""

    IDLE = "idle"
    CLEANING = "cleaning"
    PAUSED = "paused"
    RETURNING = "returning"
    REMOTE_CONTROL = "remote_control"


@dataclass(frozen=True, slots=True)
class WinbotStatus:
    """Last known robot status. None means not reported yet."""

    battery_level: int | None = None  # 0-5 steps
    charging: bool | None = None
    powered: bool | None = None  # isEnergize
    battery_low: bool | None = None
    attached: bool | None = None  # adsorption (suction on)
    state: str | None = None  # raw: idle / clean / move
    trigger: str | None = None  # raw: button / app / workComplete
    router: str | None = None  # raw clean mode
    motion_state: str | None = None  # working / pause
    border: int | None = None
    duration: int | None = None
    direction: str | None = None
    error_codes: tuple[int, ...] = ()
    auto_spray: bool | None = None
    volume: int | None = None  # voice volume 0-63
    out_of_water: bool | None = None  # only known from onSprayInfo
    serial_number: str | None = None
    firmware: str | None = None  # SVER
    model_id: str | None = None  # MID
    # The whole getRobotInfo section, including BVER and VVER, whose meaning isn't known.
    robot_info: dict[str, Any] = field(default_factory=dict)
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def activity(self) -> Activity | None:
        """Return the simplified activity, or None if unknown."""
        if self.state is None:
            return None
        if self.state == "move":
            return Activity.REMOTE_CONTROL
        if self.state == "clean":
            if self.router == CleanMode.RETURN:
                return Activity.RETURNING
            if self.motion_state == "pause":
                return Activity.PAUSED
            return Activity.CLEANING
        return Activity.IDLE

    @property
    def is_active(self) -> bool:
        """Return True while the robot is doing something worth staying connected for."""
        return self.state in ("clean", "move")

    @property
    def finished(self) -> bool:
        """Return True if the last clean ended on its own."""
        return self.state == "idle" and self.trigger == "workComplete"

    @property
    def battery_percent(self) -> int | None:
        """Approximate battery percentage (the robot only reports 5 steps)."""
        return None if self.battery_level is None else self.battery_level * 20


def _bool(value: Any) -> bool | None:
    if value is None:
        return None
    return str(value) not in ("0", "False", "false", "")


def apply_section(status: WinbotStatus, name: str, data: dict[str, Any]) -> WinbotStatus:
    """Return a new status with one getX / onX section applied."""
    key = name.removeprefix("get").removeprefix("set").removeprefix("on")
    changes: dict[str, Any] = {}
    if key == "BatteryInfo":
        changes = {
            "battery_level": data.get("value"),
            "charging": _bool(data.get("isCharging")),
            "powered": _bool(data.get("isEnergize")),
            "battery_low": _bool(data.get("isLow")),
        }
    elif key == "Adsorption":
        changes = {"attached": _bool(data.get("adsorption"))}
    elif key == "CleanInfo":
        clean_state = data.get("cleanState") or {}
        changes = {
            "state": data.get("state"),
            "trigger": data.get("trigger"),
            "router": clean_state.get("router"),
            "motion_state": clean_state.get("motionState"),
            "border": clean_state.get("border"),
            "duration": clean_state.get("duration"),
            "direction": clean_state.get("direction"),
        }
        if data.get("state") == "clean" and status.state not in ("clean", None):
            # A new clean started. The robot only reports water when the tank
            # runs dry (it said nothing after a refill, a start or a spray), so
            # assume water until it says otherwise; last time it did ~20 s in.
            changes["out_of_water"] = False
    elif key == "Error":
        changes = {"error_codes": tuple(data.get("code") or ())}
    elif key == "SprayInfo":
        changes = {"auto_spray": _bool(data.get("auto"))}
        if "water" in data:
            # water 0 = out of water (confirmed by the robot's voice prompt).
            changes["out_of_water"] = not _bool(data["water"])
    elif key == "Voice":
        changes = {"volume": data.get("value")}
    elif key == "RobotInfo":
        changes = {
            "serial_number": data.get("SN"),
            "firmware": data.get("SVER"),
            "model_id": data.get("MID"),
            "robot_info": dict(data),
        }
    else:
        return replace(status, extra={**status.extra, key: data})
    return replace(status, **{k: v for k, v in changes.items() if v is not None})


def apply_info(status: WinbotStatus, data: dict[str, Any]) -> WinbotStatus:
    """Apply a full getInfo reply."""
    for name, section in data.items():
        if isinstance(section, dict):
            status = apply_section(status, name, section)
    return status


@dataclass(frozen=True, slots=True)
class WinbotStats:
    """Lifetime statistics from getBuryData.

    Only the plain counters are named. Most other fields are arrays whose positions
    aren't decoded yet (glass_count, clean_sum, key_count, ...), so they're kept in raw.
    """

    charge_count: int | None = None
    no_water_count: int | None = None
    fall_count: int | None = None
    raw: dict[str, Any] = field(default_factory=dict)


def parse_stats(data: dict[str, Any]) -> WinbotStats:
    """Parse a getBuryData reply."""

    def count(key: str) -> int | None:
        value = data.get(key)
        return value if isinstance(value, int) and not isinstance(value, bool) else None

    return WinbotStats(
        charge_count=count("charge_count"),
        no_water_count=count("no_water_count"),
        fall_count=count("fall_count"),
        raw=dict(data),
    )
