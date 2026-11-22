"""Send ONE captured control command to the Winbot and print the reply and pushes for a few seconds.

Only commands seen in the ECOVACS HOME app capture are allowed (see docs/protocol.md).

Usage: python winbot_send.py <name>
  names: wheels_forward, wheels_backward, start_depth, pause, resume, stop, return,
         spray_once, auto_spray_on, auto_spray_off
"""

import asyncio
import sys
import time

from bleak import BleakClient, BleakScanner
from winbot_query import NOTIFY, WRITE, build, crc8

DEPTH = {"duration": 0, "border": 1, "type": "depth", "direction": "normal"}
COMMANDS: dict[str, tuple[str, dict]] = {
    "wheels_forward": ("wheelsStart", {"direction": "forward"}),
    "wheels_backward": ("wheelsStart", {"direction": "backward"}),
    "start_depth": ("clean", {"act": "start", "content": {**DEPTH, "windowType": "inner"}}),
    "pause": ("clean", {"act": "pause", "content": DEPTH}),
    "resume": ("clean", {"act": "resume", "content": DEPTH}),
    "stop": ("clean", {"act": "stop", "content": {"type": "depth"}}),
    "return": ("clean", {"act": "start", "content": {"type": "return", "border": 0, "duration": 0}}),
    "spray_once": ("sprayWater", {"direction": "auto"}),
    "auto_spray_on": ("setSprayInfo", {"auto": 1}),
    "auto_spray_off": ("setSprayInfo", {"auto": 0}),
}
LISTEN = 8


async def main() -> None:
    if len(sys.argv) != 2 or sys.argv[1] not in COMMANDS:
        print(__doc__)
        return
    cmd, data = COMMANDS[sys.argv[1]]
    dev = await BleakScanner.find_device_by_filter(
        lambda d, a: (a.local_name or "").startswith("WINBOT"), timeout=30
    )
    if dev is None:
        print("WINBOT not found (asleep, or the app is connected?)")
        return
    rx = bytearray()
    t0 = time.monotonic()

    def on_notify(_s, chunk: bytearray) -> None:
        rx.extend(chunk)
        while b"\n" in rx:
            i = rx.index(b"\n")
            msg = bytes(rx[:i])
            del rx[: i + 1]
            j = msg.find(b"{")
            hdr = msg[:j].replace(b"\0", b"|").decode(errors="replace")
            ok = "ok" if crc8(msg[3:-1]) == msg[-1] else "BAD"
            print(
                f"[+{time.monotonic() - t0:4.1f}s] <- {hdr} crc={ok} {msg[j:-1].decode(errors='replace')}",
                flush=True,
            )

    async with BleakClient(dev, timeout=20) as client:
        await client.start_notify(NOTIFY, on_notify)
        await asyncio.sleep(1)  # let the on-connect onBatteryInfo push arrive first
        frame = build(cmd, data)
        print(f"[+{time.monotonic() - t0:4.1f}s] -> {frame!r}", flush=True)
        await client.write_gatt_char(WRITE, frame, response=False)
        await asyncio.sleep(LISTEN)


if __name__ == "__main__":
    asyncio.run(main())
