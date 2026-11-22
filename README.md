# Ecovacs Winbot for Home Assistant

A Home Assistant custom integration for the Ecovacs Winbot window cleaning robot, talking to it locally over Bluetooth (directly or through an ESPHome Bluetooth proxy). No Ecovacs account or cloud needed.

> [!WARNING]
> Work in progress. The integration itself isn't written yet; this repo currently holds the reverse-engineered protocol and the research tools.

## Why

The ECOVACS HOME app only talks to the Winbot over Bluetooth, and iOS suspends that connection when the app is in the background, so you never get a "cleaning finished" notification. The robot announces that moment over Bluetooth itself, so Home Assistant can listen for it and notify you instead.

## Status

- [x] Protocol reverse engineered: see [docs/protocol.md](docs/protocol.md)
- [x] Status polling (`getInfo`) and push events (`onCleanInfo`, `onBatteryInfo`, ...) verified on real hardware
- [ ] Home Assistant integration
- [ ] Control commands (start, stop, mode)

Tested on: Winbot W2 Pro Omni (firmware 2.6.0). Other Winbot models that use the ECOVACS HOME app over Bluetooth may use the same protocol, but that's untested.

## Security note

The robot doesn't use Bluetooth pairing or any login: anything within Bluetooth range can read its status, and probably control it. Nothing an integration can change.

## Research tools

`tools/` has the Python ([bleak](https://github.com/hbldh/bleak)) scripts used to work out the protocol: a GATT dump, an advertisement watcher, a PacketLogger (`.pklg`) parser, and query-only status scripts. None of them send commands that make the robot move.

## Disclaimer

Not affiliated with or endorsed by Ecovacs. Built with the help of AI ([Claude Code](https://claude.com/claude-code)) and tested on my own robot.

## License

[MIT](LICENSE)
