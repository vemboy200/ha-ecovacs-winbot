"""Ecovacs Winbot BLE protocol (to be split out into a PyPI library)."""

from .client import (
    WinbotClient,
    WinbotCommandError,
    WinbotConnectionError,
    WinbotError,
)
from .models import Activity, CleanMode, WinbotStats, WinbotStatus
from .protocol import Frame, FrameAssembler, FrameKind, crc8, decode_frame, encode_request, redact

__all__ = [
    "Activity",
    "CleanMode",
    "Frame",
    "FrameAssembler",
    "FrameKind",
    "WinbotClient",
    "WinbotCommandError",
    "WinbotConnectionError",
    "WinbotError",
    "WinbotStats",
    "WinbotStatus",
    "crc8",
    "decode_frame",
    "encode_request",
    "redact",
]
