"""Passive advertisement watcher for WINBOT/WINBASE. Prints only when the payload changes."""

import asyncio
import sys
import time

from bleak import BleakScanner

SECONDS = int(sys.argv[1]) if len(sys.argv) > 1 else 300
last: dict[str, tuple] = {}
last_seen: dict[str, float] = {}
t0 = time.monotonic()


def cb(dev, adv) -> None:
    name = adv.local_name or ""
    if not (name.startswith("WINBOT") or name.startswith("WINBASE")):
        return
    now = time.monotonic() - t0
    key = (
        name,
        tuple(sorted((k, v.hex()) for k, v in adv.manufacturer_data.items())),
        tuple(sorted((k, v.hex()) for k, v in adv.service_data.items())),
        tuple(sorted(adv.service_uuids)),
        adv.tx_power,
    )
    if last.get(dev.address) != key:
        print(f"[{now:7.1f}s] {name:20} rssi={adv.rssi:4} mfr={dict(key[1])} "
              f"svcdata={dict(key[2])} svcs={list(key[3])} tx={adv.tx_power}", flush=True)
        last[dev.address] = key
    last_seen[dev.address] = now


async def main() -> None:
    print(f"Watching {SECONDS}s. Only changes are printed.", flush=True)
    async with BleakScanner(cb):
        for _ in range(SECONDS // 10):
            await asyncio.sleep(10)
            now = time.monotonic() - t0
            for addr, seen in last_seen.items():
                if now - seen > 10:
                    print(f"[{now:7.1f}s] {addr[:8]} not heard for {now - seen:.0f}s", flush=True)


asyncio.run(main())
