"""Map the robot's buttons to getBuryData key_count positions, and show which buttons send a live message.

Usage: python -I tools/winbot_keys.py

Stays connected and prints every message the robot pushes. Press Enter to read the statistics: it prints
key_count and which positions changed since the last read. Press a robot button a few times between reads.
Type q and Enter to quit. Turn off "Bluetooth connection" in Home Assistant first.
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
REDACT = ("SN", "MAC", "DID")


def crc8(data: bytes) -> int:
    c = 0
    for b in data:
        c ^= b
        for _ in range(8):
            c = ((c << 1) ^ 0x31) & 0xFF if c & 0x80 else (c << 1) & 0xFF
    return c


def build(cmd: str, data: dict) -> tuple[str, bytes]:
    while True:
        mid = "".join(random.choices(string.ascii_uppercase, k=4))
        body = json.dumps({"body": {"data": data}}, separators=(",", ":")).encode()
        inner = cmd.encode() + b"\0" + b"12124\0" + b"q" + mid.encode() + b"\0" + b"j" + body
        crc = crc8(inner)
        if crc != 0x0A:  # the robot drops frames whose CRC is the \n terminator
            return mid, b"`FP" + inner + bytes([crc]) + b"\n"


def redact(obj):
    if isinstance(obj, dict):
        return {k: ("<redacted>" if k in REDACT else redact(v)) for k, v in obj.items()}
    if isinstance(obj, list):
        return [redact(v) for v in obj]
    return obj


async def main() -> None:
    print("looking for the robot...")
    dev = await BleakScanner.find_device_by_filter(
        lambda d, a: (a.local_name or "").startswith("WINBOT"), timeout=20
    )
    if dev is None:
        print("WINBOT not found (off, or Home Assistant still connected? turn off Bluetooth connection)")
        return
    start = time.monotonic()
    rx = bytearray()
    stats: asyncio.Queue[dict] = asyncio.Queue()

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
            except ValueError:
                continue
            data_part = body.get("body", {}).get("data", {})
            if name == "getBuryData":
                stats.put_nowait(data_part)
            else:
                print(f"{time.monotonic() - start:7.2f}s  LIVE {name} {json.dumps(redact(data_part), separators=(',', ':'))}")

    previous: list[int] | None = None
    async with BleakClient(dev) as client:
        await client.start_notify(NOTIFY, on_notify)
        start = time.monotonic()
        print("connected. Enter = read key_count, q + Enter = quit")
        loop = asyncio.get_running_loop()
        while True:
            line = await loop.run_in_executor(None, sys.stdin.readline)
            if line.strip().lower() == "q" or not line:
                break
            _, frame = build("getBuryData", {})
            await client.write_gatt_char(WRITE, frame, response=False)
            try:
                data = await asyncio.wait_for(stats.get(), 8)
            except TimeoutError:
                print("no answer to getBuryData")
                continue
            keys = data.get("key_count")
            changed = (
                ""
                if previous is None
                else "  changed: "
                + (", ".join(f"[{i}] +{n - o}" for i, (o, n) in enumerate(zip(previous, keys)) if n != o) or "nothing")
            )
            print(f"{time.monotonic() - start:7.2f}s  key_count {keys}{changed}")
            previous = keys


asyncio.run(main())
