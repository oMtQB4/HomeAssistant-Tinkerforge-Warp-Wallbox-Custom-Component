# Changelog

## 2.0.1 (2026-09-30)

- Brand icons shipped inside the integration (`brand/`)
- Services reject SoC parameters on chargers without vehicle support
- README: badges and supported hardware

## 2.0.0 (2026-09-30)

- Push updates via the charger WebSocket (`local_push`) with polling fallback
- Options flow (WebSocket toggle, poll interval) and reconfigure flow
- Meter detail, session, charge-limit, power-manager and diagnostic entities
- Switches (auto-start, boost, EV wake-up, PV excess), numbers (limits, guaranteed power, target grid power)
- Services: `set_charge_mode`, `set_charge_limits`, `set_external_current`, `inject_soc`, `inject_nfc_tag`
- Event entities (NFC tag, charge session, button), firmware update entity, reboot / DC-fault reset buttons
- Diagnostics, icon translations, quality scale, HACS packaging

## 1.0.0 (2026-09-25)

- Initial release: charge mode select, status/meter sensors, start/stop buttons, external current limit
