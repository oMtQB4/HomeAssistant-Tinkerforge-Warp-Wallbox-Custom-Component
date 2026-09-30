# WARP Charger Integration for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://hacs.xyz)
[![Validate](https://github.com/oMtQB4/HomeAssistant-Tinkerforge-Warp-Wallbox-Custom-Component/actions/workflows/validate.yml/badge.svg)](https://github.com/oMtQB4/HomeAssistant-Tinkerforge-Warp-Wallbox-Custom-Component/actions/workflows/validate.yml)
[![GitHub release](https://img.shields.io/github/v/release/oMtQB4/HomeAssistant-Tinkerforge-Warp-Wallbox-Custom-Component)](https://github.com/oMtQB4/HomeAssistant-Tinkerforge-Warp-Wallbox-Custom-Component/releases)

Custom [Home Assistant](https://www.home-assistant.io/) integration for [Tinkerforge WARP](https://warp-charger.com/)
wallboxes. It talks to the charger's HTTPS API and WebSocket directly on the local network. No cloud, no MQTT broker required.

## Supported hardware

| Model | Status | Notes |
|---|---|---|
| **WARP4 Charger** (Smart / Pro) | Tested | Development device, firmware 2.13.x. Vehicle SoC / name and SoC limits (ISO 15118) are WARP4-only. |
| **WARP3 Charger** (Smart / Pro) | Expected to work | Same HTTP/WebSocket API. Untested, feedback welcome. |
| **WARP2 Charger** (Smart / Pro) | Expected to work | Same API. Untested. |
| **WARP1 Charger** (Smart / Pro) | Probably works | Same API surface; entities that need a hardware feature (DC fault, EV wake-up, meter) are only created when the charger reports it. Untested. |
| **WARP Energy Manager** (WEM / WEM2) | Not supported | No EVSE; discovery ignores it. |

Requirements: firmware 2.x with the HTTP API enabled (default). *Smart* variants without an energy meter get no power/energy entities.
The charge-mode list follows what the charger offers (`charge_manager/supported_charge_modes`), so PV/Eco modes appear only when
they are enabled in the WARP web interface.
## Features

- **Push updates** via the charger's WebSocket (`/ws`) with HTTP polling as fallback (`iot_class: local_push`).
- **Charge mode** select (Fast / Off / PV / Min + PV / Eco …) — options follow what the charger currently supports.
- Sensors: charger state, power, energy (energy-dashboard ready), session energy/duration/user, last session,
  per-phase current/voltage/power, frequency, grid power, available power, vehicle name and SoC (WARP4/ISO 15118),
  charge-limit targets, diagnostics (uptime, error state, DC fault, network, NTP).
- Controls: start/stop charging, external current limit, energy/duration/SoC limits, auto-start, boost mode,
  EV wake-up, PV excess charging, minimum charging power, target grid power, reboot, DC fault reset.
- Events: NFC tag presented, charge session started/ended, front button pressed.
- Firmware **update entity** with install support.
- Services: `warp_charger.set_charge_mode`, `set_charge_limits`, `set_external_current`, `inject_soc`, `inject_nfc_tag`.
- Config flow with zeroconf discovery, re-authentication, reconfigure and options (poll interval, WebSocket on/off).
- Diagnostics download (credentials redacted), German and English translations.

## Installation

### HACS
Add `https://github.com/oMtQB4/HomeAssistant-Tinkerforge-Warp-Wallbox-Custom-Component` as a custom repository (category *Integration*), install **WARP Charger**, restart Home Assistant.

### Manual
Copy `custom_components/warp_charger/` from this repository to `config/custom_components/warp_charger/` and restart Home Assistant.

## Setup

*Settings → Devices & services → Add integration → WARP Charger* (or accept the discovered device).

| Parameter | Description |
|---|---|
| Host | IP address (recommended) or hostname of the charger. The charger redirects to HTTPS automatically. |
| Username / Password | Required when *HTTP authentication* is enabled on the charger (Digest auth). |
| Verify SSL certificate | Off by default; the charger ships a self-signed certificate. |

Options (gear icon on the integration): *Push updates via WebSocket* (default on) and *Polling interval* used
while the WebSocket is down (default 10 s). While the WebSocket is connected a safety poll runs every 120 s.

For the external current limit and start/stop to work, enable **External control** under *Charger → Settings*
in the WARP web interface.

## Data updates

The charger pushes every state change over the WebSocket; the integration coalesces bursts (250 ms) before updating
entities. Configuration topics (limits, power manager settings, users) are refreshed every 6th poll or whenever the
charger pushes them.

## Known limitations

- The integration keeps one WebSocket open; the ESP32 supports only a few concurrent WebSocket clients (each open
  WARP web UI tab uses one).
- Entities are created at setup based on what the charger reports. Enabling features later (e.g. external control,
  a vehicle profile) requires reloading the integration.
- `0 A` on the external current entity cannot be set via the number (minimum 6 A); use the
  `set_external_current` service with `0` or the *Off* charge mode to block charging.
- SoC limits can only be set as default limits, not as a per-session override.

## Troubleshooting

- **Entities unavailable**: check that the host is reachable (`https://<host>/info/name`) and that credentials
  match the WARP web UI. A 401 triggers the re-authentication flow.
- **No push updates**: the `WebSocket connected` diagnostic binary sensor shows the link state. Enable debug
  logging with `logger.logs: custom_components.warp_charger: debug`.
- Download diagnostics from the device page to see the raw topic cache.

## Removal

Delete the integration entry under *Settings → Devices & services*, then remove the `warp_charger` folder.

## Example automation

```yaml
alias: Fast charge when leaving early
triggers:
  - trigger: time
    at: "05:30:00"
actions:
  - action: warp_charger.set_charge_mode
    data:
      device_id: !input charger
      mode: fast
```
