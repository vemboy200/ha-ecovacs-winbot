"""Stay connected, poll getInfo every N seconds, print what changed plus any unsolicited messages.

Query-only: never sends a command that makes the robot do anything.
"""

import asyncio
import json
import sys
import time

from bleak import BleakClient, BleakScanner
from winbot_query import NOTIFY, WRITE, build, crc8

INTERVAL = int(sys.argv[1]) if len(sys.argv) > 1 else 10
t0 = time.monotonic()
pending: set[str] = set()
last: dict = {}


def stamp() -> str:
    return f"[{time.strftime('%H:%M:%S')} +{time.monotonic() - t0:6.0f}s]"


def flatten(d, prefix=""):
    for k, v in d.items():
        if isinstance(v, dict):
            yield from flatten(v, f"{prefix}{k}.")
        else:
            yield f"{prefix}{k}", v


def handle(msg: bytes) -> None:
    hdr = msg[3 : msg.index(b"{")]
    cmd = hdr.split(b"\0")[0].decode()
    mid = hdr.split(b"\0")[2][1:].decode() if hdr.count(b"\0") >= 2 else "?"
    payload = json.loads(msg[msg.index(b"{") : -1])
    crc = "ok" if crc8(msg[3:-1]) == msg[-1] else "BAD"
    if mid in pending and cmd == "getInfo":
        pending.discard(mid)
        flat = dict(flatten(payload["body"].get("data", {})))
        changes = {k: v for k, v in flat.items() if last.get(k) != v and not k.startswith("getRobotInfo")}
        if changes:
            print(stamp(), "CHANGED", json.dumps(changes), flush=True)
        last.update(flat)
    else:
        print(stamp(), f"UNSOLICITED cmd={cmd} hdr={hdr!r} crc={crc}", json.dumps(payload), flush=True)


async def main() -> None:
    while True:
        dev = await BleakScanner.find_device_by_filter(
            lambda d, a: (a.local_name or "").startswith("WINBOT"), timeout=30
        )
        if dev is None:
            print(stamp(), "WINBOT not advertising, retrying", flush=True)
            continue
        rx = bytearray()

        def on_notify(_s, data: bytearray) -> None:
            rx.extend(data)
            while b"\n" in rx:
                i = rx.index(b"\n")
                msg = bytes(rx[:i])
                del rx[: i + 1]
                try:
                    handle(msg)
                except Exception as err:
                    print(stamp(), "unparsed", msg, err, flush=True)

        try:
            async with BleakClient(dev, timeout=20) as client:
                print(stamp(), "connected", flush=True)
                await client.start_notify(NOTIFY, on_notify)
                while client.is_connected:
                    frame = build("getInfo", {"timestamp": int(time.time())})
                    pending.add(frame.split(b"\0")[2][1:5].decode())
                    await client.write_gatt_char(WRITE, frame, response=False)
                    await asyncio.sleep(INTERVAL)
        except Exception as err:
            print(stamp(), "connection lost:", err, flush=True)
        print(stamp(), "disconnected, reconnecting", flush=True)


asyncio.run(main())
