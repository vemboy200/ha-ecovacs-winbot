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
- Push messages start with `` `FR `` instead of `` `FP `` (seen on an `onBatteryInfo` sent right after connecting; the earlier pushes weren't logged with their first 3 bytes). The CRC still covers everything after those 3 bytes. Parse on the 3-byte prefix being `` `F `` + one letter until more is known.
- The robot sent an `onBatteryInfo` push immediately after a fresh connection, before any request.

Request JSON: `{"body":{"data":{...}}}`. Reply/push JSON: `{"body":{"code":0,"msg":"ok","data":{...}}}` (`code`/`msg` sometimes absent on pushes).

## Commands

### `getInfo`

Request data: `{"timestamp": <unix seconds>}`. Reply data contains:

| Key | Fields seen | Notes |
|---|---|---|
| `getBatteryInfo` | `value`, `isCharging`, `isEnergize`, `isLow` | `value` is a 5-step level (5 = full, 4 ≈ 80%), not a percentage. `isEnergize` 1 while powered |
| `getAdsorption` | `adsorption` (string `"0"`/`"1"`) | `"1"` = suction on, attached to glass |
| `getRobotInfo` | `SN`, `MAC`, `DID`, `MID`, `VVER`, `SVER`, `BVER` | Device identity and firmware. `SVER` is the main firmware (`getOTAStatus.ver` matches it). `BVER` (`K13_V316.03.08`) and `VVER` (`10.0.8`) are unknown: `BVER` shares the `K13_V316` prefix with the Bluetooth module's own software revision (`K13_V316.02.01`) but not the number, and the app logs both under a `VoiceSetting` tag, so `VVER` may be the voice pack (*guess*). The Bluetooth module's Device Information service reports hardware revision `V1.0.0`; that's the module, not the robot. `MID` is Ecovacs's product class id, also in the advertised name: a random code per product and region (`b7oysg` = W2 Pro Omni, `W2_STATION_HIGH_LEVEL_AMR`). Names for the Winbot ids are in `custom_components/ecovacs_winbot/winbot/products.py`, from Ecovacs's product catalog (`pim/product/getProductIotMap`) as saved by ecovacs-deebot.js |
| `getCleanInfo` | `state`, `trigger`, `cleanState{router, motionState, direction, border, duration}` | See below |
| `getError` | `code` (list) | `[0]` = no error |
| `getOTAStatus` | `status`, `progress`, `ver` | |
| `getSprayInfo` | `auto` | |
| `getVoice` | `using`, `support`, `value` | |
| `getGlassType` | `type`, `area` | |

### `getBuryData`

Request data `{}`. Lifetime statistics. Reply from 2026-11-22:

```
glass_count [24,0,20,0,0]      glass_scale [2,11,2,18,0]     glass_area 1600
clean_sum [15,0,93,0,0,0,0,41,67]   key_count [1,11,6,0,140,0]   lowBattery [0,0,0,0,0]
battery_temp [293,306]   finally_mode [0,0]   advise_cuccess 1388
charge_count 31   no_water_count 6   fall_count 0   fall_Time 0   motor_die_count 0
err_data: three arrays of 13 (one value, 1763942912, looks like a Unix timestamp)
```

The integration shows `charge_count`, `no_water_count` and `fall_count` as sensors, since their names say what they count. *Not known:* what each position in the arrays means, the unit of `glass_area`, what the two `battery_temp` values are (kelvin, see below), and what `motor_die_count` counts. Diagnostics include the whole reply, to help decode these.

Second reading, 2026-11-23 about 4:45 PM local (robot indoors, about 68 °F; 62 °F outside), compared with the first:

| Field | 2026-11-22 | 2026-11-23 | Reading |
|---|---|---|---|
| `no_water_count` | 6 | 8 | Up by 2, and the robot reported out of water twice in between. **Confirmed** as the out-of-water count |
| `charge_count` | 31 | 35 | Several plug-ins in between, consistent with a charge count |
| `battery_temp` | [293, 306] | [293, 306] | **Kelvin**: 20 °C / 68 °F and 33 °C / 91 °F. Tenths of a degree Celsius would mean the battery never read below 84 °F, even after the robot sat outside at 62 °F. Unchanged after cleans, a charge and time outside, so not a live temperature. *Not known:* whether it's the lifetime low and high or values saved at some event; a reading after a clearly hotter or colder spell would tell |
| `glass_count` | [24,0,20,0,0] | [34,0,29,0,0] | Positions 0 and 2 grew by 10 and 9 |
| `glass_scale` | [2,11,2,18,0] | [2,11,2,29,0] | Position 3 grew by 11 |
| `clean_sum` | [15,0,93,0,0,0,0,41,67] | [17,0,94,3,0,0,0,41,76] | Positions 0, 2, 3 and 8 grew |
| `key_count` | [1,11,6,0,140,0] | [1,11,10,0,150,0] | Button presses, mapped below |
| `finally_mode` | [0,0] | [0,3] | |
| `advise_cuccess` | 1388 | 1452 | |
| `err_data` | | | Three rows of 13. *Reading:* per error type, row 0 and 2 a count and row 1 the Unix time it last happened. Position 4: 2 times, last 2025-11-24 00:08 UTC. Position 2 is new: 2 times, last 2026-11-22 21:39 UTC (during the first tests) |

**`key_count` mapped** (2026-11-23, pressing each button and reading again with `tools/winbot_keys.py`):

| Position | Button | Live message when pressed |
|---|---|---|
| 0 | not one of the W2 Pro Omni's four buttons (value 1) | |
| 1 | Power (+2 for off and on) | None; the robot just stops or starts advertising |
| 2 | Cleaning mode (+1 per press) | `onCleanInfo` with the new `router` |
| 3 | not one of the four (value 0) | |
| 4 | Cable reel (+1 per press) | **None**: the counter is the only trace |
| 5 | not one of the four (value 0) | |

The start/pause button (it starts a clean, which begins with suction) isn't counted anywhere in `key_count`; it shows up live as `onCleanInfo` state `clean` / `idle` with trigger `button`. Positions 0, 3 and 5 may be buttons on other models or on the station.

### `XLog`

The app sends its own log lines to the robot (`{"level","tag","message"}`). No need to copy this.

## Control commands (captured from the app, 2026-11-22)

All of these got `code: 0` replies or the matching `onCleanInfo` push. None have been replayed from our own code yet.

### `clean`

The main command. Request data: `{"act": <act>, "content": {...}}`.

| `act` | `content` seen | Result |
|---|---|---|
| `start` | `{"duration":0,"windowType":"inner","border":1,"type":"depth","direction":"normal"}` | Starts a clean. `onCleanInfo` state `clean`, trigger `app`, router = `type` |
| `pause` | `{"duration":0,"border":1,"type":"depth","direction":"normal"}` | motionState → `pause` (state stays `clean`) |
| `resume` | same as pause | motionState → `working` |
| `stop` | `{"type":"spot"}` | state → `idle`, trigger `app` (**not** `workComplete`) |

`content` fields for `start`:

| Field | Values seen | Meaning |
|---|---|---|
| `type` | `depth`, `border`, `spot`, `return` | Cleaning mode. `return` = go back (it ended with `workComplete` about a second later) |
| `border` | `0`, `1` | Edge cleaning on/off (*reading*; the app toggled it alongside mode changes) |
| `duration` | `0`, `5`, `10` | Timed clean in minutes: `10` = the app's 10-minute timed clean (user confirmed), `5` = the 5-minute clean (sent from HA, the robot ran it and echoed `duration: 5`), `0` = until done. Echoed in `cleanState.duration` |
| `windowType` | `inner` | Only `inner` seen; absent for `spot` and `return` |
| `direction` | `normal`, `left`, `right` | Starting direction (*reading*) |

Sending `start` again while cleaning switches mode immediately; no need to stop first.

The robot never sends a reply frame for `clean` (0 replies to the app's 14 requests). It answers with an `onCleanInfo` push within about 0.3 s instead, so wait for that push rather than a reply.

### Other commands

| Command | Data | Reply | Notes |
|---|---|---|---|
| `setVoice` | `{"value": 0-63}` | `{using, support, value}` | Voice volume. The app sent 7, 14, 21. A 0-100 sweep from HA: 0-63 accepted and echoed, anything higher clamped to 63. The robot beeps at the new volume each time |
| `setSprayInfo` | `{"auto": 0 \| 1}` | `{auto}` | Automatic spraying off/on |
| `sprayWater` | `{"direction": "auto"}` | `{success: 1}` | Spray once now |
| `wheelsStart` | `{"direction": "forward" \| "backward"}` | `code 0` | *Unknown* app button (wheel cleaning?); no state change seen |
| `wheelMove` | `{"angle": 360, "speed": 2, "act": "move"}` | none | Remote-control driving: sent every ~100 ms while the joystick is held; `angle` 360 and 180 seen. State goes to `move`, router `control`. See [Remote control](#remote-control) |

### Checksum quirk

The app's `clean` / `return` request had a wrong CRC (0x6a instead of 0x60), and the robot still carried it out. So the robot may not check the CRC on requests. Always send the correct one anyway.

**A CRC byte of `0x0A` makes the robot drop the request.** `0x0A` is the `\n` terminator, so the robot apparently sees the frame end one byte early. Found in the volume sweep (3 of 101 requests unanswered) and confirmed by forcing the CRC to `0x0A`: 3 of 3 dropped, while 3 normal requests right after were answered. The message ID is part of the CRC, so pick a new ID until the CRC isn't `0x0A`. Frames from the robot can also end in a `0x0A` CRC, so don't split incoming data on `\n` alone.

## Push events seen

| Event | Data | When |
|---|---|---|
| `onBatteryInfo` | same as `getBatteryInfo` | Charging stopped; level dropped 5 → 4 |
| `onCleanInfo` | same as `getCleanInfo` | Clean started, mode changed, clean finished |
| `onAdsorption` | `adsorption` | Suction turned on at start |
| `onGlassType` | `type`, `area` | Shortly after start |
| `onSprayInfo` | `auto`, `water` | Mid-clean; `water: 0` = **out of water** (the robot's voice said so at the same moment). Never sent with water present: nothing after a refill, a clean start, a manual spray, or a finished clean with a full tank. `water` can't be polled either: `getSprayInfo` (alone or in `getInfo`) only returns `auto` |
| `onCollision` | `direction` | Seen once, `{"direction": "br,"}`, right after a clean finished and just before suction turned off, as the robot was taken off the glass. The trailing comma suggests a list. Every edge, corner and both bumpers give the same `br,` (see [Remote control](#remote-control)), so it doesn't say which side |

## Clean state values seen

| `state` | `trigger` | Meaning |
|---|---|---|
| `idle` | `button` | Idle (last action was a button press) |
| `clean` | `button` | Cleaning, started with the robot's button |
| `idle` | `workComplete` | **Cleaning finished** (also after a `return`) |
| `clean` | `app` | Cleaning, started or changed from the app |
| `idle` | `app` | Stopped from the app |
| `idle` | `button` | Also: stopped with the robot's button mid-clean |
| `move` | `app` | Remote-control driving (router `control`) |

Pause shows as state `clean` with motionState `pause`. A stop from the app or button is `idle` + `app`/`button`, never `workComplete`, so a "finished" event can key on `workComplete` alone.

- `cleanState.router`: `depth`, `auto`, `border`, `spot`, `return`, `control` seen; pressing the mode button switched depth → auto. `border` went 1 → 0 at the same time (*meaning unconfirmed*).
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

## Switching off on the charger (2026-11-23)

The robot was plugged in already full (battery LEDs steady, which on this robot means full; blinking means charging), with Home Assistant connected through a Bluetooth proxy. About 10 minutes later the robot switched itself off: the LEDs went dark, Home Assistant's connection dropped, reconnect attempts got no answer, and it stopped advertising. So the robot powers off by itself once it's full, and an open connection doesn't keep it on.

`isCharging` stayed 1 the whole time, so it follows the plug rather than whether the battery is still charging, and the robot can't be asked whether it's full. One test so far; how long it waits after reaching full from a lower charge isn't known.

## Remote control

The ECOVACS HOME app needs a cloud account and an internet connection even to drive the robot over Bluetooth, so local remote control in Home Assistant would replace the app's joystick entirely. Not built yet.

**Known** (app capture 2026-11-22, and `tools/winbot_drive.py` on the window 2026-11-23, robot attached to the glass):

- The app sends `wheelMove {"angle": <n>, "speed": 2, "act": "move"}` about every 100 ms while the joystick is held, and the robot doesn't reply. Sending the same from a script works without the app.
- The robot pushes `onCleanInfo` state `move`, router `control`, trigger `app` about 0.2 s after the first `wheelMove`.
- **It stops by itself.** About 1.1 to 1.3 s after the last `wheelMove` it pushes state `idle` (router back to `auto`), in all 14 runs (speeds 1 to 5, bursts of 0.5 to 2 s). So a dropped connection mid-move leaves it stopped within about a second, and no stop message is needed.
- **`angle` is a direction on the window, in degrees:** 360 up, 180 down, 90 right, 270 left. The robot first turns to face that way, then drives. It may reverse instead of turning around: facing right, 270 made it back up to the left.
- **`angle` isn't limited to four directions:** 45 made it turn toward the upper right and drive diagonally.
- **`speed` is 1 to 3**, faster as it goes up (the app was seen sending 2). 4 and 5 were accepted but looked slower than 3, about the same as each other, so values above 3 seem to fall back to a slower speed. The robot never replies to `wheelMove`, so an out-of-range value gives no error.
- **`onCollision` is always `{"direction": "br,"}`**: driving into the right, top and bottom edges, into the top-right corner diagonally, and tapping either of the two bumpers by hand all gave the same code. So it doesn't say which side. *Reading:* `br` means "bumper". Each hit while driving gave one message and the robot went idle about a second later. Once, left pressed against the right edge, it repeated about once a second; bumper taps while it sat idle may report nothing.

**Not known yet:**

- Whether the app varies `speed` with how far the joystick is pushed, and exactly what speed 4 and above fall back to.
- Whether the app sends anything on release (no capture of that yet), and whether other `act` values exist.
- How well a 100 ms stream works through an ESPHome Bluetooth proxy (the script talked to the robot directly from a Mac).

**Plan for Home Assistant** (smallest pieces first):

1. A `remote` entity, like TV integrations use, with `up`, `down`, `left` and `right` commands (angles 360, 180, 270, 90) at a fixed speed. Since the robot stops by itself, a dropped connection is safe. `remote.send_command` already takes `hold_secs`, so the integration repeats `wheelMove` every 100 ms for that long, then stops. Enabled by default, with a copy-paste D-pad dashboard card in the README. Home Assistant's dashboard has no hold-to-drive control (a tap fires once, `hold_action` fires once with no release event), so from a dashboard each tap is a nudge, not the app's continuous joystick.
2. Since the angle is analog (45 worked): an entity action like `ecovacs_winbot.drive` with validated `angle` (0 to 360), `speed` (1 to 3) and `duration` fields, for scripts and custom cards. Not raw protocol through `vacuum.send_command`.

## Not yet known

- What `wheelsStart` is.
- Other `state` / `trigger` values (error, fell off, low battery).
- What `border` and `glass_type` values mean, and what `water` reads when the tank has water.
- Whether the station (`WINBASE`) has anything useful.
