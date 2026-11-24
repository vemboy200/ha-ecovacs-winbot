"""Keyboard remote control for the Winbot, to test edge collisions. Prints every message the robot pushes.

Usage: python -I tools/winbot_joystick.py

  arrows or W A S D   drive up / left / down / right (hold the key to keep going)
  Q E Z C             diagonals: up-left / up-right / down-left / down-right
  1 2 3               speed (1 slow, 3 fast; starts at 2)
  X or Ctrl-C         quit

Holding a key relies on the keyboard's auto-repeat, and the robot stops by itself about a second after
the last command, so letting go stops it. Turn off "Bluetooth connection" in Home Assistant first: the
robot accepts one connection at a time.
"""

import asyncio
import json
import os
import random
import string
import sys
import termios
import time
import tty

from bleak import BleakClient, BleakScanner

NOTIFY = "0000fff1-0000-1000-8000-00805f9b34fb"
WRITE = "0000fff2-0000-1000-8000-00805f9b34fb"
INTERVAL = 0.1  # the app sends wheelMove every ~100 ms while the joystick is held
HOLD = 0.6  # keep driving this long after the last key press (covers the auto-repeat delay)
REDACT = ("SN", "MAC", "DID")

KEYS = {
    "\x1b[A": 360, "w": 360,
    "\x1b[B": 180, "s": 180,
    "\x1b[C": 90, "d": 90,
    "\x1b[D": 270, "a": 270,
    "q": 315, "e": 45, "z": 225, "c": 135,
}
NAMES = {360: "up", 180: "down", 90: "right", 270: "left", 315: "up-left", 45: "up-right", 225: "down-left", 135: "down-right"}


def crc8(data: bytes) -> int:
    c = 0
    for b in data:
        c ^= b
        for _ in range(8):
            c = ((c << 1) ^ 0x31) & 0xFF if c & 0x80 else (c << 1) & 0xFF
    return c


def build(cmd: str, data: dict) -> bytes:
    while True:
        mid = "".join(random.choices(string.ascii_uppercase, k=4))
        body = json.dumps({"body": {"data": data}}, separators=(",", ":")).encode()
        inner = cmd.encode() + b"\0" + b"12124\0" + b"q" + mid.encode() + b"\0" + b"j" + body
        crc = crc8(inner)
        if crc != 0x0A:  # the robot drops frames whose CRC is the \n terminator
            return b"`FP" + inner + bytes([crc]) + b"\n"


def redact(obj):
    if isinstance(obj, dict):
        return {k: ("<redacted>" if k in REDACT else redact(v)) for k, v in obj.items()}
    if isinstance(obj, list):
        return [redact(v) for v in obj]
    return obj


def say(text: str) -> None:
    # The terminal is in raw mode, so lines need \r\n.
    sys.stdout.write(text + "\r\n")
    sys.stdout.flush()


async def main() -> None:
    say("looking for the robot...")
    dev = await BleakScanner.find_device_by_filter(
        lambda d, a: (a.local_name or "").startswith("WINBOT"), timeout=20
    )
    if dev is None:
        say("WINBOT not found (off, or Home Assistant still connected? turn off Bluetooth connection)")
        return
    start = time.monotonic()
    rx = bytearray()

    def on_notify(_s, data: bytearray) -> None:
        rx.extend(data)
        while b"\n" in rx:
            i = rx.index(b"\n")
            msg = bytes(rx[:i])
            del rx[: i + 1]
            if b"{" not in msg:
                continue
            name = msg[3 : msg.index(b"{")].split(b"\0")[0].decode(errors="replace")
            try:
                body = json.loads(msg[msg.index(b"{") : -1])
                data_part = redact(body.get("body", {}).get("data", body))
            except ValueError:
                data_part = msg[msg.index(b"{") : -1].decode(errors="replace")
            marker = "  <<< COLLISION" if name == "onCollision" else ""
            say(f"{time.monotonic() - start:7.2f}s  {name} {json.dumps(data_part, separators=(',', ':'))}{marker}")

    angle: int | None = None
    speed = 2
    last_key = 0.0
    quit_event = asyncio.Event()
    buf = ""

    def on_key() -> None:
        nonlocal angle, speed, last_key, buf
        buf += os.read(sys.stdin.fileno(), 32).decode(errors="ignore")
        while buf:
            if buf[0] == "\x1b":
                if len(buf) < 3:
                    return  # wait for the rest of the arrow sequence
                key, buf = buf[:3], buf[3:]
            else:
                key, buf = buf[0].lower(), buf[1:]
            if key in ("x", "\x03"):
                quit_event.set()
            elif key in "123" and len(key) == 1:
                speed = int(key)
                say(f"speed {speed}")
            elif key in KEYS:
                if KEYS[key] != angle or time.monotonic() - last_key > HOLD:
                    say(f"{time.monotonic() - start:7.2f}s  -> {NAMES[KEYS[key]]} (angle {KEYS[key]}, speed {speed})")
                angle = KEYS[key]
                last_key = time.monotonic()

    async with BleakClient(dev) as client:
        await client.start_notify(NOTIFY, on_notify)
        old = termios.tcgetattr(sys.stdin)
        tty.setraw(sys.stdin.fileno())
        loop = asyncio.get_running_loop()
        loop.add_reader(sys.stdin.fileno(), on_key)
        start = time.monotonic()
        say("connected. arrows/WASD drive, QEZC diagonals, 1-3 speed, X quits")
        try:
            while not quit_event.is_set():
                if angle is not None and time.monotonic() - last_key <= HOLD:
                    await client.write_gatt_char(
                        WRITE, build("wheelMove", {"angle": angle, "speed": speed, "act": "move"}), response=False
                    )
                await asyncio.sleep(INTERVAL)
        finally:
            loop.remove_reader(sys.stdin.fileno())
            termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old)
    print("disconnected (the robot stops by itself within about a second)")


try:
    asyncio.run(main())
except KeyboardInterrupt:
    pass
