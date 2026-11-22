"""Send query-only commands (getInfo by default) to the Winbot and print the JSON replies.

Frame (from the iOS capture):  b"`FP" + cmd + b"\0" + b"12124\0" + b"q" + id4 + b"\0" + b"j" + json + crc8 + b"\n"
crc8 = poly 0x31, init 0, no reflection, over everything after b"`FP" up to the CRC byte.
Replies use b"p" instead of b"q" and echo the 4-letter id.
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
QUERY_ONLY = {"getInfo", "getBuryData"}


def crc8(data: bytes) -> int:
    c = 0
    for b in data:
        c ^= b
        for _ in range(8):
            c = ((c << 1) ^ 0x31) & 0xFF if c & 0x80 else (c << 1) & 0xFF
    return c


def build(cmd: str, data: dict) -> bytes:
    mid = "".join(random.choices(string.ascii_uppercase, k=4))
    body = json.dumps({"body": {"data": data}}, separators=(",", ":")).encode()
    inner = cmd.encode() + b"\0" + b"12124\0" + b"q" + mid.encode() + b"\0" + b"j" + body
    return b"`FP" + inner + bytes([crc8(inner)]) + b"\n"


async def main() -> None:
    cmds = sys.argv[1:] or ["getInfo"]
    assert set(cmds) <= QUERY_ONLY, f"only query commands allowed: {QUERY_ONLY}"
    dev = await BleakScanner.find_device_by_filter(
        lambda d, a: (a.local_name or "").startswith("WINBOT"), timeout=20
    )
    if dev is None:
        print("WINBOT not found (asleep, or connected elsewhere?)")
        return
    rx = bytearray()
    done = asyncio.Event()

    def on_notify(_s, data: bytearray) -> None:
        rx.extend(data)
        while b"\n" in rx:
            i = rx.index(b"\n")
            msg = bytes(rx[:i])
            del rx[: i + 1]
            ok = crc8(msg[3:-1]) == msg[-1]
            j = msg[msg.index(b"{") : -1]
            print(f"<- crc_ok={ok} {msg[3 : msg.index(b'{')]!r}")
            try:
                print(json.dumps(json.loads(j), indent=1))
            except ValueError:
                print(j)
            done.set()

    async with BleakClient(dev, timeout=20) as client:
        await client.start_notify(NOTIFY, on_notify)
        for cmd in cmds:
            data = {"timestamp": int(time.time())} if cmd == "getInfo" else {}
            frame = build(cmd, data)
            print(f"-> {frame!r}")
            done.clear()
            for i in range(0, len(frame), 180):
                await client.write_gatt_char(WRITE, frame[i : i + 180], response=False)
            try:
                await asyncio.wait_for(done.wait(), 5)
            except TimeoutError:
                print("no reply in 5s")


if __name__ == "__main__":
    asyncio.run(main())
