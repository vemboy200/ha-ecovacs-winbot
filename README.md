# Ecovacs Winbot for Home Assistant

A Home Assistant custom integration for the Ecovacs Winbot window cleaning robot. It talks to the robot locally over Bluetooth, either from the Home Assistant machine's own Bluetooth adapter or through an [ESPHome Bluetooth proxy](https://esphome.io/components/bluetooth_proxy.html). No Ecovacs account, cloud or app is needed.

> [!WARNING]
> Early version, Platinum on the [quality scale](https://www.home-assistant.io/docs/quality_scale/) (self-assessed: every rule is done or exempt, see [quality_scale.yaml](custom_components/ecovacs_winbot/quality_scale.yaml)). Status, push events, the cleaning events and the controls (start, pause, stop, return, every cleaning mode, volume) have been tested from Home Assistant on real hardware. Remote-control driving was tested from a script on a Mac with the same messages, not yet through Home Assistant. Expect changes.

## Why

The ECOVACS HOME app only talks to the Winbot over Bluetooth, and iOS suspends that connection when the app is in the background, so you never get a "cleaning finished" notification. The robot announces that moment over Bluetooth itself, so Home Assistant can listen for it and notify you instead.

## Supported devices

**Wi-Fi and Bluetooth**

- Winbot W3 Omni: untested (Ecovacs lists both Bluetooth and Wi-Fi control)
- Newer models, as they come out: untested

**Bluetooth only**

- Winbot W2 Pro Omni (firmware 2.6.0): tested
- Winbot Mini: untested (reviews say it doesn't join Wi-Fi)

**Bluetooth, Wi-Fi not confirmed either way**

- Winbot W2 Pro Omni 7-11: untested
- Winbot W2s Omni: untested
- Winbot W2s: untested
- Winbot W2 Pro: untested
- Winbot W2 Omni: untested
- Winbot W2: untested
- Winbot W1s: untested
- Winbot W1 Pro: untested
- Glassbot W1 Pro: untested
- Winbot Neo: untested
- Winbot Neo Mini: untested
- Winbot Mini 2: untested
- Winbot Lite: untested
- Winbot 920: untested

**No app connection**

- Winbot X and older models, which use a remote control instead of the app: not supported

All the Bluetooth models come from Ecovacs's product catalog, which lists every Winbot as a Bluetooth product, the W3 Omni included, so it doesn't say which ones also have Wi-Fi. If you know one of them does, please say so. Untested models may use the same protocol; please open an issue either way. This integration only talks to the robot over Bluetooth, so on models that can also join Wi-Fi and the Ecovacs cloud, those features aren't used. Home Assistant's built-in [Ecovacs integration](https://www.home-assistant.io/integrations/ecovacs/) works over the cloud, but its library only knows Deebot vacuums and GOAT mowers, not Winbots. Models with Wi-Fi, like the W3 Omni, could in theory be supported by it one day, since they can reach the Ecovacs cloud, but they aren't as of today. Bluetooth-only models never reach the cloud on their own, so this integration is the only way to get them into Home Assistant.

The device page shows the model, looked up from the model id the robot reports (the W2 Pro Omni reports `b7oysg` or one of several other ids, depending on where it was sold). The table of ids comes from Ecovacs's product catalog and covers every Winbot in it as of November 2026, from the 920 to the W3 Omni. If yours shows just "Winbot", it's a newer id: please open an issue with the **Model ID** from the device page.

The robot advertises as `WINBOT_<id>_<nnnn>`. The Omni station (`WINBASE_...`) is not used.

**Other Ecovacs Bluetooth devices**

Ecovacs's Ultramarine P1 pool robot is also controlled over Bluetooth with the ECOVACS HOME app (retailers list it without Wi-Fi). Whether it uses the same protocol as the Winbots isn't known, so it's not supported, and since Bluetooth drops while it's underwater, Home Assistant could only reach it out of the water. If you own one and are willing to help find out, please open an issue. If it turns out to work the same way, the plan is to support it here under a broader display name, such as "Ecovacs Bluetooth", while keeping the `ecovacs_winbot` domain so existing setups don't break.

## Requirements

- Home Assistant 2026.9 or newer.
- Home Assistant with the [Bluetooth integration](https://www.home-assistant.io/integrations/bluetooth/) working, through a local adapter or an ESPHome Bluetooth proxy that supports active connections.
- The robot within Bluetooth range of that adapter or proxy. A signal around -80 dBm or better is comfortable; near -90 dBm connections time out.

## Installation

### Through the Marketplace (or HACS)

1. In Home Assistant, go to **Settings** > **Marketplace** and select **Add from link**. On Home Assistant 2026.10 or older, add it as a custom repository (type **Integration**) in HACS instead.
2. Enter `vemboy200/ha-ecovacs-winbot` and add it.
3. Install **Ecovacs Winbot** and restart Home Assistant.

### Manual

1. Copy `custom_components/ecovacs_winbot` into your Home Assistant `config/custom_components/` folder.
2. Restart Home Assistant.

## Configuration

1. Turn the Winbot on and close the ECOVACS HOME app (the robot only accepts one connection).
2. Home Assistant should discover it: go to **Settings → Devices & services** and click **Configure** on the discovered **Winbot**. Or click **Add integration**, search for **Ecovacs Winbot**, and pick the robot from the list.
3. Home Assistant connects to the robot and reads its status before adding it. If that fails, you get "Couldn't connect to the Winbot": check that it's on, that the app is closed, and that it's in range, then try again.

### Installation parameters

| Parameter | Description |
|---|---|
| Robot | The Winbot to add, chosen from the robots Home Assistant can currently hear over Bluetooth. Only shown when adding it manually; discovery fills it in. |

There are no options to configure afterwards.

## Entities

| Entity | Type | Description |
|---|---|---|
| Winbot (vacuum) | Vacuum | Start (resumes if paused), pause, stop, return, spot clean. **Fan speed** is the cleaning mode: Deep, Edge, Spot, 5 minutes, 10 minutes. Picking a mode sets what Start uses, or switches immediately mid-clean. Like the app, the commands only work while the robot is attached to the glass (otherwise they give an error); picking a mode works any time |
| Status | Sensor | Off, Idle, Cleaning, Paused, Returning, Remote control. "Off" means the robot isn't advertising (switched off or out of range) |
| Battery | Sensor | Battery level. The robot reports 5 steps, so this moves in 20% steps |
| Cleaning mode | Sensor | Mode the robot reports: Deep, Auto, Edge, Spot, Return, Remote control |
| Cleaning | Event | Fires **Started** (`started`) when a clean starts, with `source` `button` (the robot's own button) or `app` (the ECOVACS HOME app or Home Assistant; the robot doesn't tell them apart), **Done cleaning** (`finished`) when a clean completes on its own, **Done returning** (`returned`) when a return completes, **Interrupted** when the robot goes off mid-clean, **Error** when it reports an error (it stops when that happens; the codes are in the event's `error_codes` attribute), **Out of water** (`out_of_water`) when the robot reports its tank ran dry (once per clean; the Out of water binary sensor shows the same thing as a state) |
| Bumper | Event (disabled by default) | Fires **Bumped** when the robot reports hitting something, with the robot's `code` (always `br,` so far). It doesn't say which edge or bumper: every edge, a corner and both bumpers gave the same code. It repeats about once a second while the robot presses against the frame |
| Charging | Binary sensor | Whether the battery is charging |
| Attached to glass | Binary sensor | Whether suction is on, which is when the robot is on the window. The vacuum commands, driving and Spray need it |
| Out of water | Binary sensor | On when the robot reports an empty tank. The robot only says so in a message during a clean (the full status doesn't include it), so the last value is kept, also across Home Assistant restarts, until the robot reports again. Unknown until the first report. The robot doesn't report a refilled tank (nothing after a refill, a start or a spray), so the sensor turns off when a new clean starts and back on if the robot reports the tank empty again |
| Spray | Button | Spray once. Unavailable while the robot isn't attached to the glass |
| Automatic spraying | Switch | Let the robot spray on its own while cleaning |
| Voice volume | Number | Volume of the robot's voice prompts, 0-63 (the app was seen sending 7, 14 and 21). The robot beeps at the new volume when it changes |
| Bluetooth connection | Switch | Whether Home Assistant uses the robot's Bluetooth connection. Turn it off to make Home Assistant disconnect and stay off, so the ECOVACS HOME app or another device can connect (see below) |
| Last trigger | Sensor (diagnostic, disabled by default) | What the robot says caused its last state change: Robot button, App or Home Assistant (the robot doesn't tell them apart), or Work complete. The same value is also the Status sensor's `last_trigger` attribute |
| Error code | Sensor (diagnostic) | Raw error codes; `0` means no error |
| Charge count, Out of water count, Fall count | Sensor (diagnostic) | Lifetime counters the robot keeps: how many times it was charged, ran out of water, and fell (the robot's `fall_count`, which has stayed at 0 so far). The robot reports more statistics (windows and area cleaned, button presses, battery temperature), but their layout isn't decoded yet; they're included in diagnostics |
| Signal strength | Sensor (diagnostic) | Bluetooth signal of the robot's advertisements, as heard by the best adapter or proxy |

While the robot is off, everything except Status, Cleaning, Bluetooth connection and Signal strength shows as unavailable.

## How data is updated

- **On or off** comes from the robot's Bluetooth advertisements. No connection is needed for that.
- **While the robot is on**, Home Assistant stays connected. The robot pushes every change (started, mode changed, error, battery, charging, out of water, finished) the moment it happens, including cleans started from the robot's own button.
- **Backup:** Home Assistant also asks for the full status (`getInfo`) every 60 seconds while cleaning and every 2 minutes while idle, and reconnects if the connection dropped.
- **After 15 minutes idle**, Home Assistant lets go of the robot and stops checking, so the robot can switch itself off. Idle means no cleaning, no presses of the robot's buttons and no commands from Home Assistant; battery updates don't count. While it's charging Home Assistant stays connected, and the 15 minutes start when it's unplugged. The connection doesn't keep it on: once the battery is full, the robot switches itself off on the charger anyway (seen about 10 minutes after it was plugged in already full), and Home Assistant shows it as Off a few minutes later. It connects again when the robot is switched back on or when you use any of its controls in Home Assistant.
- **Every new connection** starts by reading the full status.
- **Signal strength** comes from the robot's advertisements, not the connection. It's refreshed every 60 seconds while cleaning and every 2 minutes otherwise, including while Home Assistant has let go or Bluetooth connection is off, and right away when it moves by 3 dBm or more in an advertisement Home Assistant passes on.
- **Lifetime counters** are read when Home Assistant connects, after a clean finishes and when charging starts, since they don't change otherwise.

Because the robot accepts only one Bluetooth connection at a time, the ECOVACS HOME app (or anything else) can't connect while Home Assistant is connected. Turn off **Bluetooth connection** for that.

### Bluetooth connection

Turning this switch off makes Home Assistant disconnect and stop connecting, so another device, such as a phone with the ECOVACS HOME app, can use the robot. Status (on/off) and signal strength keep updating, because they only need advertisements. The other sensors keep their last values, the controls are unavailable, and no Cleaning events fire while it's off. Turn it back on and Home Assistant reconnects and reads the full status. It resets to on when Home Assistant restarts.

While it's on, Home Assistant still lets go after 15 minutes idle (see above), so on means Home Assistant may connect, not that it's connected right now.

This switch replaced **Let the app connect** (which worked the other way round: on meant Home Assistant stayed off). The old switch is removed on upgrade; update any automations or dashboards that used it.

### Remote control

The **Drive** action (below) drives the robot without the app, like the app's joystick. The robot first turns to face the direction, then drives, and it may back up instead of turning around. It stops by itself about a second after the last move message, also if the connection drops, and stops when it bumps into the frame.

Home Assistant's dashboard has no hold-to-drive control (a button fires once when tapped and once when held, with nothing on release), so from a dashboard each press is one drive of a fixed length, not the app's continuous joystick.

An 8-way D-pad for a dashboard, using the built-in grid and button cards, with the robot's status in the middle (tap an arrow for a nudge of about a second, hold it for 2 seconds of driving; replace the entity IDs with yours):

```yaml
type: grid
columns: 3
square: true
cards:
  - type: button
    icon: mdi:arrow-top-left
    show_name: false
    tap_action:
      action: perform-action
      perform_action: ecovacs_winbot.drive
      target:
        entity_id: vacuum.winbot_0bc4
      data:
        angle: 315
        duration: 0
    hold_action:
      action: perform-action
      perform_action: ecovacs_winbot.drive
      target:
        entity_id: vacuum.winbot_0bc4
      data:
        angle: 315
        duration: 2
  - type: button
    icon: mdi:arrow-up
    show_name: false
    tap_action:
      action: perform-action
      perform_action: ecovacs_winbot.drive
      target:
        entity_id: vacuum.winbot_0bc4
      data:
        angle: 360
        duration: 0
    hold_action:
      action: perform-action
      perform_action: ecovacs_winbot.drive
      target:
        entity_id: vacuum.winbot_0bc4
      data:
        angle: 360
        duration: 2
  - type: button
    icon: mdi:arrow-top-right
    show_name: false
    tap_action:
      action: perform-action
      perform_action: ecovacs_winbot.drive
      target:
        entity_id: vacuum.winbot_0bc4
      data:
        angle: 45
        duration: 0
    hold_action:
      action: perform-action
      perform_action: ecovacs_winbot.drive
      target:
        entity_id: vacuum.winbot_0bc4
      data:
        angle: 45
        duration: 2
  - type: button
    icon: mdi:arrow-left
    show_name: false
    tap_action:
      action: perform-action
      perform_action: ecovacs_winbot.drive
      target:
        entity_id: vacuum.winbot_0bc4
      data:
        angle: 270
        duration: 0
    hold_action:
      action: perform-action
      perform_action: ecovacs_winbot.drive
      target:
        entity_id: vacuum.winbot_0bc4
      data:
        angle: 270
        duration: 2
  - type: button
    entity: sensor.winbot_0bc4_status
    show_name: false
    show_state: true
    tap_action:
      action: more-info
  - type: button
    icon: mdi:arrow-right
    show_name: false
    tap_action:
      action: perform-action
      perform_action: ecovacs_winbot.drive
      target:
        entity_id: vacuum.winbot_0bc4
      data:
        angle: 90
        duration: 0
    hold_action:
      action: perform-action
      perform_action: ecovacs_winbot.drive
      target:
        entity_id: vacuum.winbot_0bc4
      data:
        angle: 90
        duration: 2
  - type: button
    icon: mdi:arrow-bottom-left
    show_name: false
    tap_action:
      action: perform-action
      perform_action: ecovacs_winbot.drive
      target:
        entity_id: vacuum.winbot_0bc4
      data:
        angle: 225
        duration: 0
    hold_action:
      action: perform-action
      perform_action: ecovacs_winbot.drive
      target:
        entity_id: vacuum.winbot_0bc4
      data:
        angle: 225
        duration: 2
  - type: button
    icon: mdi:arrow-down
    show_name: false
    tap_action:
      action: perform-action
      perform_action: ecovacs_winbot.drive
      target:
        entity_id: vacuum.winbot_0bc4
      data:
        angle: 180
        duration: 0
    hold_action:
      action: perform-action
      perform_action: ecovacs_winbot.drive
      target:
        entity_id: vacuum.winbot_0bc4
      data:
        angle: 180
        duration: 2
  - type: button
    icon: mdi:arrow-bottom-right
    show_name: false
    tap_action:
      action: perform-action
      perform_action: ecovacs_winbot.drive
      target:
        entity_id: vacuum.winbot_0bc4
      data:
        angle: 135
        duration: 0
    hold_action:
      action: perform-action
      perform_action: ecovacs_winbot.drive
      target:
        entity_id: vacuum.winbot_0bc4
      data:
        angle: 135
        duration: 2
```

## Actions

### Drive (`ecovacs_winbot.drive`)

Drives the robot toward any direction. Target the Winbot's vacuum entity. Only works while the robot is attached to the glass.

| Field | Required | Description |
|---|---|---|
| `angle` | Yes | Direction on the window in degrees: 0 or 360 up, 90 right, 180 down, 270 left, or anything in between (45 drives diagonally up and right) |
| `speed` | No | 1 (slow) to 3 (fast). Default 2, the speed the app uses |
| `duration` | No | Seconds to keep driving, 0 to 10. Default 1. 0 is a nudge of about a second |

```yaml
action: ecovacs_winbot.drive
target:
  entity_id: vacuum.winbot_0bc4
data:
  angle: 45
  speed: 3
  duration: 2
```

## Use cases

- Get a phone notification when the robot finishes a window, instead of watching it.
- Get notified when it runs out of water or stops with an error, so you can come back and fix it before it sits stuck on the glass.
- Start a clean from a dashboard or a voice assistant, and pick a mode.
- Track the battery so it's charged before the next window.

## Examples

Notify when a clean finishes, runs out of water, or stops with an error (replace the entity IDs and notify service with yours). Done returning (`returned`) is left out on purpose; add it to the list if you want that too:

```yaml
automation:
  - alias: "Winbot finished or stopped"
    triggers:
      - trigger: state
        entity_id: event.winbot_0bc4_cleaning
    conditions:
      - condition: template
        value_template: "{{ trigger.to_state.attributes.event_type in ['finished', 'error', 'interrupted'] }}"
    actions:
      - action: notify.mobile_app_my_phone
        data:
          title: "Winbot"
          message: >
            {% set t = trigger.to_state.attributes.event_type %}
            {% if t == 'finished' %}Done cleaning the window.
            {% elif t == 'error' %}Stopped with error {{ trigger.to_state.attributes.error_codes }}.
            {% else %}Turned off in the middle of a clean.{% endif %}

  - alias: "Winbot out of water"
    triggers:
      - trigger: state
        entity_id: binary_sensor.winbot_0bc4_out_of_water
        to: "on"
    actions:
      - action: notify.mobile_app_my_phone
        data:
          title: "Winbot"
          message: "Out of water. Refill the tank."
```

A script that starts a 10-minute clean:

```yaml
script:
  winbot_quick_clean:
    alias: "Winbot quick clean"
    sequence:
      - action: vacuum.set_fan_speed
        target:
          entity_id: vacuum.winbot_0bc4
        data:
          fan_speed: "10 minutes"
      - action: vacuum.start
        target:
          entity_id: vacuum.winbot_0bc4
```

## Known limitations

- **One connection at a time.** Home Assistant stays connected while the robot is on, so the ECOVACS HOME app can't connect. Turn off **Bluetooth connection** when you need the app.
- **Short Bluetooth range.** Ecovacs quotes about 5 m for the app. Through a proxy, expect connection timeouts if the signal is around -90 dBm; move the robot or the proxy closer.
- **A clean started from the robot's button after 15 minutes idle isn't seen** if the robot was left on. Home Assistant has let go by then and only reconnects when the robot is switched off and on again or a control is used.
- **Events are only seen while connected.** If the connection drops (weak signal) and the robot finishes or errors before Home Assistant gets back in, the Done cleaning event fires on the next status check only if Home Assistant knew a clean was running, and an error that already cleared is missed.
- **Battery is 5 steps**, not a real percentage.
- **Error codes aren't decoded yet.** The robot reports numeric codes; they're shown as-is and logged.
- **Not available yet:** voice language, the Omni station.
- **Remote control drives for a set time.** There's no hold-to-drive control in Home Assistant's dashboard, and each drive is limited to 10 seconds. A new drive waits for the one before it to finish, and so do other commands sent meanwhile. Driving through an ESPHome Bluetooth proxy hasn't been tested yet, and what the robot does with a drive command during a clean isn't known.
- **No authentication on the robot.** Anything within Bluetooth range can read its status and probably control it. Nothing an integration can change.

## Troubleshooting

**The robot isn't discovered / "No Winbot found".** Turn it on, close the ECOVACS HOME app, and make sure an adapter or proxy is in range. Check **Settings → Devices & services → Bluetooth → Advertisement monitor** for a `WINBOT_` device or the robot's address.

**Status shows Off while the robot is on.** Home Assistant isn't hearing its advertisements: it's out of range of every adapter and proxy, or the app is connected to it. Check the **Signal strength** history for how close to the limit it was.

**Entities are unavailable but Status isn't Off.** Home Assistant hears the robot but hasn't managed to read its status. Look for connection timeouts in the log (below); they usually mean weak signal.

**The ECOVACS HOME app can't connect.** Home Assistant holds the connection while the robot is on. Turn off **Bluetooth connection**.

**Diagnostics.** Go to **Settings → Devices & services → Ecovacs Winbot**, open the menu (⋮) on the robot's entry and choose **Download diagnostics**. It has the connection state, the last status and every version the robot reports (firmware `SVER`, plus `BVER` and `VVER`, whose meaning isn't known yet), with the serial number, device id and Bluetooth address removed. Attach it when you open an issue.

**Debug logs.** Add this to `configuration.yaml`, restart, and include the log when you open an issue. New error codes and unknown messages from the robot are logged as warnings even without debug logging.

```yaml
logger:
  logs:
    custom_components.ecovacs_winbot: debug
```

## Removal

1. Go to **Settings → Devices & services → Ecovacs Winbot**, open the menu (⋮) on the robot's entry and choose **Delete**.
2. If you installed it through the Marketplace (or HACS), uninstall **Ecovacs Winbot** there and restart Home Assistant. If you installed it manually, delete `config/custom_components/ecovacs_winbot` and restart.

The robot keeps working with the ECOVACS HOME app as before.

## How it works

The Winbot speaks small JSON messages over a Bluetooth serial-style channel. The protocol was worked out from Bluetooth logs of the ECOVACS HOME app and is documented in [docs/protocol.md](docs/protocol.md). `tools/` has the Python ([bleak](https://github.com/hbldh/bleak)) scripts used for that: a GATT dump, an advertisement watcher, a PacketLogger (`.pklg`) parser, query-only status scripts, and `winbot_send.py`, which sends one of the captured control commands.

## Disclaimer

Not affiliated with or endorsed by Ecovacs. The Ecovacs name and logo are trademarks of Ecovacs Robotics. Built with the help of AI ([Claude Code](https://claude.com/claude-code)) and tested on my own robot.

## License

[MIT](LICENSE)
