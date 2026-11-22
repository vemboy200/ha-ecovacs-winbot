"""Read-only GATT dump for the Ecovacs Winbot. Never writes to the device."""

import asyncio
import sys
import time

from bleak import BleakClient, BleakScanner

MFR_ID = 30337  # 0x7681, seen in the ratgdo advertisement
SVC = "0000fff0-0000-1000-8000-00805f9b34fb"
LISTEN_SECONDS = int(sys.argv[1]) if len(sys.argv) > 1 else 20


async def main() -> None:
    print("Scanning 15s...")
    found = await BleakScanner.discover(timeout=15, return_adv=True)
    target = None
    for dev, adv in found.values():
        if MFR_ID in adv.manufacturer_data or SVC in adv.service_uuids:
            print(
                f"MATCH {dev.address} name={adv.local_name!r} rssi={adv.rssi} "
                f"mfr={ {k: v.hex() for k, v in adv.manufacturer_data.items()} } "
                f"svcs={adv.service_uuids}"
            )
            target = dev
    if target is None:
        print(f"No Winbot found among {len(found)} devices.")
        return

    async with BleakClient(target, timeout=20) as client:
        print(f"Connected, MTU={client.mtu_size}")
        notify_chars = []
        for svc in client.services:
            print(f"\nService {svc.uuid} ({svc.description})")
            for ch in svc.characteristics:
                print(f"  Char {ch.uuid} handle={ch.handle} props={ch.properties} ({ch.description})")
                if "read" in ch.properties:
                    try:
                        val = await client.read_gatt_char(ch)
                        print(f"    value hex={val.hex()} ascii={val!r}")
                    except Exception as err:
                        print(f"    read failed: {err}")
                if "notify" in ch.properties or "indicate" in ch.properties:
                    notify_chars.append(ch)
                for d in ch.descriptors:
                    print(f"    Desc {d.uuid} handle={d.handle}")

        t0 = time.monotonic()

        def make_cb(uuid):
            def cb(_sender, data: bytearray) -> None:
                print(f"[{time.monotonic() - t0:7.2f}s] NOTIFY {uuid[4:8]} hex={data.hex()}")

            return cb

        for ch in notify_chars:
            try:
                await client.start_notify(ch, make_cb(ch.uuid))
                print(f"Subscribed to {ch.uuid}")
            except Exception as err:
                print(f"Subscribe to {ch.uuid} failed: {err}")
        print(f"\nListening {LISTEN_SECONDS}s for unsolicited notifications...")
        await asyncio.sleep(LISTEN_SECONDS)


asyncio.run(main())
