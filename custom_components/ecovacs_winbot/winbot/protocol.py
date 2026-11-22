"""Winbot BLE framing: build requests, split and decode incoming frames.

See docs/protocol.md. No Home Assistant imports here: this package is meant to
move into its own PyPI library.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import json
import random
import string
from typing import Any

MAGIC_REQUEST = b"`FP"
PROTOCOL_ID = b"12124"
TERMINATOR = 0x0A


class FrameKind(StrEnum):
    """What kind of frame this is."""

    REQUEST = "request"
    REPLY = "reply"
    PUSH = "push"


@dataclass(frozen=True, slots=True)
class Frame:
    """A decoded frame."""

    kind: FrameKind
    command: str
    msg_id: str | None
    body: dict[str, Any]
    crc_ok: bool

    @property
    def data(self) -> dict[str, Any]:
        """Return body.data (empty dict when missing)."""
        return self.body.get("data") or {}

    @property
    def code(self) -> int | None:
        """Return body.code, the robot's result code (0 = ok)."""
        return self.body.get("code")


def crc8(data: bytes) -> int:
    """CRC-8, polynomial 0x31, init 0, no reflection, no final XOR."""
    crc = 0
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = ((crc << 1) ^ 0x31) & 0xFF if crc & 0x80 else (crc << 1) & 0xFF
    return crc


def new_msg_id() -> str:
    """Return a random 4-letter message id, like the app uses."""
    return "".join(random.choices(string.ascii_uppercase, k=4))


def encode_request(command: str, data: dict[str, Any], msg_id: str) -> bytes:
    """Build a request frame, including the CRC and terminator."""
    body = json.dumps({"body": {"data": data}}, separators=(",", ":")).encode()
    inner = command.encode() + b"\0" + PROTOCOL_ID + b"\0q" + msg_id.encode() + b"\0j" + body
    return MAGIC_REQUEST + inner + bytes([crc8(inner)]) + b"\n"


def decode_frame(raw: bytes) -> Frame:
    """Decode one frame (without its trailing newline). Raises ValueError."""
    if len(raw) < 6 or raw[:2] != b"`F":
        raise ValueError(f"not a Winbot frame: {raw[:20]!r}")
    start = raw.index(b"{")
    header = raw[3:start].split(b"\0")
    body = json.loads(raw[start:-1])
    crc_ok = crc8(raw[3:-1]) == raw[-1]
    command = header[0].decode()
    if len(header) >= 4:
        kind = FrameKind.REPLY if header[2][:1] == b"p" else FrameKind.REQUEST
        return Frame(kind, command, header[2][1:].decode(), body.get("body", {}), crc_ok)
    return Frame(FrameKind.PUSH, command, None, body.get("body", {}), crc_ok)


class FrameAssembler:
    """Collect notification chunks and return complete frames.

    Frames end with CRC + newline, but the CRC itself can be 0x0A, so a newline
    only ends a frame when the JSON before the CRC byte parses.
    """

    def __init__(self) -> None:
        """Initialize an empty buffer."""
        self._buf = bytearray()

    def feed(self, chunk: bytes) -> list[Frame]:
        """Add a chunk and return any frames it completed."""
        self._buf.extend(chunk)
        frames: list[Frame] = []
        search_from = 0
        while (end := self._buf.find(TERMINATOR, search_from)) != -1:
            candidate = bytes(self._buf[:end])
            try:
                frame = decode_frame(candidate)
            except ValueError:
                if not self._buf.startswith(b"`F"):
                    # Garbage before a frame start: drop up to the next frame.
                    nxt = self._buf.find(b"`F", 1)
                    del self._buf[: nxt if nxt != -1 else len(self._buf)]
                    search_from = 0
                    continue
                search_from = end + 1
                continue
            frames.append(frame)
            del self._buf[: end + 1]
            search_from = 0
        if len(self._buf) > 16384:
            self._buf.clear()
        return frames
