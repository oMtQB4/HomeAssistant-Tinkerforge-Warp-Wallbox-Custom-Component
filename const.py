"""Constants for the WARP Charger integration."""

from __future__ import annotations

from datetime import timedelta
import logging

DOMAIN = "warp_charger"
LOGGER = logging.getLogger(__package__)

DEFAULT_HOST = "192.168.178.15"
CONF_VERIFY_SSL = "verify_ssl"

SCAN_INTERVAL = timedelta(seconds=10)
REQUEST_TIMEOUT = 10.0
# The ESP32 web server has a small socket budget; keep concurrency low.
MAX_CONCURRENCY = 2
# The WARP HTTP API accepts PUT and POST for writes; single switch point.
WRITE_METHOD = "PUT"

# ConfigChargeMode enum of the esp32-firmware -> select option slug.
# Mode 4 ("Default") is deliberately absent: it is a resolver, not a real mode.
CHARGE_MODE_MAP: dict[int, str] = {
    0: "fast",
    1: "off",
    2: "pv",
    3: "min_pv",
    5: "min",
    6: "eco",
    7: "eco_pv",
    8: "eco_min",
    9: "eco_min_pv",
}
CHARGE_MODE_REVERSE_MAP: dict[str, int] = {v: k for k, v in CHARGE_MODE_MAP.items()}

CHARGER_STATE_MAP: dict[int, str] = {
    0: "not_connected",
    1: "waiting_for_release",
    2: "ready",
    3: "charging",
    4: "error",
}

IEC61851_STATE_MAP: dict[int, str] = {
    0: "disconnected",
    1: "connected",
    2: "charging",
    3: "charging_ventilation",
    4: "error",
}

# MeterValueID (esp32-firmware meter_value_id.csv)
METER_ID_POWER = 74  # active power sum, W
METER_ID_ENERGY_IMPORT = 209  # active energy import, kWh

# API topics
T_INFO_NAME = "info/name"
T_INFO_VERSION = "info/version"
T_INFO_DISPLAY_NAME = "info/display_name"
T_CHARGE_MODE = "power_manager/charge_mode"
T_SUPPORTED_MODES = "charge_manager/supported_charge_modes"
T_EVSE_STATE = "evse/state"
T_EXTERNAL_ENABLED = "evse/external_enabled"
T_EXTERNAL_CURRENT = "evse/external_current"
T_START_CHARGING = "evse/start_charging"
T_STOP_CHARGING = "evse/stop_charging"
T_METER_IDS = "meters/0/value_ids"
T_METER_VALUES = "meters/0/values"
T_CURRENT_CHARGE = "charge_tracker/current_charge"
T_EV_STATE = "ev/state"
