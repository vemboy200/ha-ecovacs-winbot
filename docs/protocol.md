# Ecovacs Winbot BLE protocol (W2 Pro Omni)

Reverse engineered on 2026-11-22 from an iOS PacketLogger capture of the ECOVACS HOME app, then checked live with the scripts in `tools/`. Tested on one robot only: Winbot W2 Pro Omni, firmware SVER 2.6.0, BVER K13_V316.03.08, VVER 10.0.8, model id (MID) `b7oysg`.

Anything marked *unconfirmed* is a reading of the data, not something we've tested.

## Devices

| Advertised name | What it is | Manufacturer data | Notes |
|---|---|---|---|
| `WINBOT_<mid>_<nnnn>` | The robot | company id 30337 (`0x7681`), data = last 4 bytes of the MAC | The app talks only to this one |
| `WINBASE_<mid>_<nnnn>` | The Omni station | company id 5505, data `0002a30d` | Advertises only sometimes; not used by the app in our capture |

Both advertise service `0000fff0-…`. The advertisements carry no state.

The robot's BLE module reports manufacturer `WLT`, model `WLT8016M`, and a serial ending in `_115200`, which looks like a transparent BLE-to-UART bridge (*unconfirmed*).

**No authentication:** no pairing, bonding or login. A fresh connection can send `getInfo` and gets an answer.

**One connection at a time (likely):** while a Mac held the connection, the ECOVACS HOME app couldn't connect.

## GATT

| Service | Characteristic | Properties | Use |
|---|---|---|---|
| `fff0` | `fff1` (value handle 0x1b, CCCD 0x1c) | notify | Robot → host messages |
| `fff0` | `fff2` (value handle 0x1f) | write without response | Host → robot messages |
| `ffe0` | `ffe1` / `ffe2` | notify / write without response | Not used by the app |
| `02f00000-0000-0000-0000-00000000fe00` | `ff00`–`ff03` | various (`ff02` reads `ntf_enable`) | Probably module config / OTA; leave alone |

The robot asks for an MTU of 517. Messages longer than one notification are split across several; reassemble until the trailing `\n`.

## Framing

```
request:  "`FP" + cmd + "\0" + "12124\0" + "q" + ID + "\0" + "j" + JSON + CRC + "\n"
reply:    "`FP" + cmd + "\0" + "12124\0" + "p" + ID + "\0" + "j" + JSON + CRC + "\n"
push:     "`FP" + cmd + "\0" + "j" + JSON + CRC + "\n"
```

- `ID` is 4 random uppercase ASCII letters; the reply echoes it.
- `12124` was the same in every message (app's and robot's); it's probably a fixed protocol or app id, not a secret.
- `CRC` is one byte: CRC-8, polynomial `0x31`, init `0x00`, no reflection, no final XOR, computed over everything after `` `FP `` up to (not including) the CRC byte. Matches every message captured.
- Push messages are unsolicited, named `on…`, and have no `12124` or ID.

Request JSON: `{"body":{"data":{...}}}`. Reply/push JSON: `{"body":{"code":0,"msg":"ok","data":{...}}}` (`code`/`msg` sometimes absent on pushes).

## Commands

### `getInfo`

Request data: `{"timestamp": <unix seconds>}`. Reply data contains:

| Key | Fields seen | Notes |
|---|---|---|
| `getBatteryInfo` | `value`, `isCharging`, `isEnergize`, `isLow` | `value` is a 5-step level (5 = full, 4 ≈ 80%), not a percentage. `isEnergize` 1 while powered |
| `getAdsorption` | `adsorption` (string `"0"`/`"1"`) | `"1"` = suction on, attached to glass |
| `getRobotInfo` | `SN`, `MAC`, `DID`, `MID`, `VVER`, `SVER`, `BVER` | Device identity and firmware |
| `getCleanInfo` | `state`, `trigger`, `cleanState{router, motionState, direction, border, duration}` | See below |
| `getError` | `code` (list) | `[0]` = no error |
| `getOTAStatus` | `status`, `progress`, `ver` | |
| `getSprayInfo` | `auto` | |
| `getVoice` | `using`, `support`, `value` | |
| `getGlassType` | `type`, `area` | |

### `getBuryData`

Request data `{}`. Lifetime statistics: `glass_count`, `glass_scale`, `glass_area`, `clean_sum`, `charge_count`, `no_water_count`, `battery_temp`, `err_data`, and more.

### `XLog`

The app sends its own log lines to the robot (`{"level","tag","message"}`). No need to copy this.

## Push events seen

| Event | Data | When |
|---|---|---|
| `onBatteryInfo` | same as `getBatteryInfo` | Charging stopped; level dropped 5 → 4 |
| `onCleanInfo` | same as `getCleanInfo` | Clean started, mode changed, clean finished |
| `onAdsorption` | `adsorption` | Suction turned on at start |
| `onGlassType` | `type`, `area` | Shortly after start |
| `onSprayInfo` | `auto`, `water` | Mid-clean; `water: 0` = **out of water** (the robot's voice said so at the same moment). Value with water present not seen yet (presumably 1) |

## Clean state values seen

| `state` | `trigger` | Meaning |
|---|---|---|
| `idle` | `button` | Idle (last action was a button press) |
| `clean` | `button` | Cleaning, started with the robot's button |
| `idle` | `workComplete` | **Cleaning finished** |

- `cleanState.router`: `depth` and `auto` seen; pressing the mode button switched depth → auto. `border` went 1 → 0 at the same time (*meaning unconfirmed*).
- `cleanState.motionState`: `pause` while idle before the run, `working` during it, and it **stayed `working` after `workComplete`**. Don't use it to detect the end.
- `cleanState.duration` stayed `0` the whole run.

## First full clean (2026-11-22, about 4 minutes)

```
12:32:22 onCleanInfo   state=clean trigger=button router=depth motionState=working
12:32:23 onAdsorption  "1"
12:32:47 onGlassType   type=0 area=0
12:32:56 onBatteryInfo value 5 -> 4
12:34:38 onCleanInfo   router depth -> auto, border 1 -> 0   (mode button pressed)
12:35:15 onSprayInfo   auto=1 water=0   (voice prompt: out of water)
12:36:10 onCleanInfo   state=idle trigger=workComplete
```

A `getInfo` poll every 10 s saw every change within one interval.

## Not yet known

- Commands that make the robot act (start, stop, change mode). Not captured or tried.
- Other `state` / `trigger` values (paused, error, fell off, low battery, started from the app).
- What `border` and `glass_type` values mean, and what `water` reads when the tank has water.
- Whether the station (`WINBASE`) has anything useful.
