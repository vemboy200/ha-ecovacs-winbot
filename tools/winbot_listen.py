"""Listen-only: subscribe to FFF1 and print every message. Never writes anything.

getInfo replies (the poller's answers, if macOS shares the link) are shown as one short line;
everything else is printed in full and marked PUSH?.
"""

import asyncio
import json
import time

from bleak import BleakClient, BleakScanner

from winbot_query import NOTIFY, crc8

t0 = time.monotonic()


def stamp() -> str:
    return f"[{time.strftime('%H:%M:%S')} +{time.monotonic() - t0:6.0f}s]"


async def main() -> None:
    while True:
        dev = await BleakScanner.find_device_by_filter(
            lambda d, a: (a.local_name or "").startswith("WINBOT"), timeout=30)
        if dev is None:
            # Already connected by the poller: macOS may not show it advertising; try known devices.
            print(stamp(), "WINBOT not advertising, retrying", flush=True)
            continue
        rx = bytearray()

        def on_notify(_s, data: bytearray) -> None:
            rx.extend(data)
            while b"\n" in rx:
                i = rx.index(b"\n")
                msg = bytes(rx[:i]); del rx[: i + 1]
                try:
                    hdr = msg[3:msg.index(b"{")]
                    parts = hdr.split(b"\0")
                    cmd, kind = parts[0].decode(), parts[2][:1].decode()
                    mid = parts[2][1:].decode()
                    crc = "ok" if crc8(msg[3:-1]) == msg[-1] else "BAD"
                    body = json.loads(msg[msg.index(b"{"):-1])
                    if cmd == "getInfo" and kind == "p":
                        st = body["body"]["data"].get("getCleanInfo", {})
                        print(stamp(), f"poll reply id={mid} state={st.get('state')} "
                              f"motion={st.get('cleanState', {}).get('motionState')}", flush=True)
                    else:
                        print(stamp(), f"PUSH? cmd={cmd} kind={kind} id={mid} crc={crc}",
                              json.dumps(body), flush=True)
                except Exception as err:  # noqa: BLE001
                    print(stamp(), "unparsed", msg, err, flush=True)

        try:
            async with BleakClient(dev, timeout=20) as client:
                print(stamp(), "connected, listening only", flush=True)
                await client.start_notify(NOTIFY, on_notify)
                while client.is_connected:
                    await asyncio.sleep(1)
        except Exception as err:  # noqa: BLE001
            print(stamp(), "connection lost:", err, flush=True)
        print(stamp(), "disconnected, reconnecting", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
