"""Self-stop test: send wheelMove like the app's joystick for a short burst, then stop sending and listen.

Usage: python -I tools/winbot_drive.py [angle] [seconds] [speed]   (default 360 for 1 s at speed 2, at most 2 s)

Sends {"angle": <angle>, "speed": 2, "act": "move"} every 100 ms for BURST_SECONDS, exactly as the app
did while the joystick was held, then sends nothing and prints the robot's pushes for LISTEN_SECONDS.
Watch whether the wheels stop on their own when the messages stop.

The robot moves: put it flat on the floor with room around it, not on a table.
"""

import asyncio
import json
import random
import string
import sys
import time

from bleak import BleakClient, BleakScanner

NOTIFY = "0000fff1-0000-1000-8000-00805f9b34fb"
WRITE = "0000fff2-0000-1000-8000-00805f9b34fb"
BURST_SECONDS = 1.0
MAX_BURST_SECONDS = 2.0
INTERVAL = 0.1
LISTEN_SECONDS = 5.0
REDACT = ("SN", "MAC", "DID")


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


def redact(text: str) -> str:
    try:
        obj = json.loads(text)
    except ValueError:
        return text

    def walk(o):
        if isinstance(o, dict):
            return {k: ("<redacted>" if k in REDACT else walk(v)) for k, v in o.items()}
        if isinstance(o, list):
            return [walk(v) for v in o]
        return o

    return json.dumps(walk(obj), separators=(",", ":"))


async def main() -> None:
    angle = int(sys.argv[1]) if len(sys.argv) > 1 else 360
    burst = min(float(sys.argv[2]) if len(sys.argv) > 2 else BURST_SECONDS, MAX_BURST_SECONDS)
    speed = int(sys.argv[3]) if len(sys.argv) > 3 else 2  # the app was only seen sending 2
    dev = await BleakScanner.find_device_by_filter(
        lambda d, a: (a.local_name or "").startswith("WINBOT"), timeout=20
    )
    if dev is None:
        print("WINBOT not found (off, or connected elsewhere?)")
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
            head = msg[3 : msg.index(b"{")].split(b"\0")[0].decode(errors="replace").lstrip("`FPR")
            print(f"{time.monotonic() - start:6.2f}s <- {head} {redact(msg[msg.index(b'{') : -1].decode(errors='replace'))}")

    async with BleakClient(dev) as client:
        await client.start_notify(NOTIFY, on_notify)
        print(f"connected; sending wheelMove angle={angle} speed={speed} for {burst}s")
        start = time.monotonic()
        while time.monotonic() - start < burst:
            await client.write_gatt_char(WRITE, build("wheelMove", {"angle": angle, "speed": speed, "act": "move"}), response=False)
            await asyncio.sleep(INTERVAL)
        print(f"{time.monotonic() - start:6.2f}s stopped sending; listening {LISTEN_SECONDS}s. Do the wheels stop?")
        await asyncio.sleep(LISTEN_SECONDS)


asyncio.run(main())
