"""Constants for the WARP Charger integration."""

from __future__ import annotations

from datetime import timedelta
import logging

DOMAIN = "warp_charger"
LOGGER = logging.getLogger(__package__)

DEFAULT_HOST = "192.168.178.15"
CONF_VERIFY_SSL = "verify_ssl"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_USE_WEBSOCKET = "use_websocket"

DEFAULT_SCAN_INTERVAL = 10
MIN_SCAN_INTERVAL = 5
MAX_SCAN_INTERVAL = 300
SCAN_INTERVAL = timedelta(seconds=DEFAULT_SCAN_INTERVAL)
# Safety-net poll while the WebSocket delivers pushes.
WS_POLL_INTERVAL = timedelta(seconds=120)
REQUEST_TIMEOUT = 10.0
# The ESP32 web server has a small socket budget; keep concurrency low.
MAX_CONCURRENCY = 2
# The WARP HTTP API accepts PUT and POST for writes; single switch point.
WRITE_METHOD = "PUT"

# WebSocket push
WS_PATH = "/ws"
WS_KEEPALIVE_TIMEOUT = 15.0
WS_BACKOFF_MIN = 1.0
WS_BACKOFF_MAX = 60.0
WS_DEBOUNCE_COOLDOWN = 0.25

# Polling tiers (fallback path). Medium/slow topics are fetched every Nth poll.
POLL_MEDIUM_EVERY = 3
POLL_SLOW_EVERY = 6

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

ERROR_STATE_MAP: dict[int, str] = {
    0: "ok",
    2: "switch_error",
    3: "dc_fault",
    4: "contactor_error",
    5: "communication_error",
}

DC_FAULT_STATE_MAP: dict[int, str] = {
    0: "ok",
    1: "residual_6ma",
    2: "system_error",
    3: "unknown_error",
    4: "calibration_error",
    5: "ac_error",
    6: "ac_dc_error",
}

CONNECTION_STATE_MAP: dict[int, str] = {
    0: "not_configured",
    1: "not_connected",
    2: "connecting",
    3: "connected",
}

# charge_limits duration enum -> slug
DURATION_LIMIT_MAP: dict[int, str] = {
    0: "unlimited",
    1: "15_min",
    2: "30_min",
    3: "45_min",
    4: "1_h",
    5: "2_h",
    6: "3_h",
    7: "4_h",
    8: "6_h",
    9: "8_h",
    10: "12_h",
}
DURATION_LIMIT_REVERSE_MAP: dict[str, int] = {v: k for k, v in DURATION_LIMIT_MAP.items()}

# MeterValueID (esp32-firmware meter_value_id.csv)
METER_ID_VOLTAGE_L1 = 1
METER_ID_VOLTAGE_L2 = 2
METER_ID_VOLTAGE_L3 = 3
METER_ID_CURRENT_L1 = 13
METER_ID_CURRENT_L2 = 17
METER_ID_CURRENT_L3 = 21
METER_ID_POWER_L1 = 39
METER_ID_POWER_L2 = 48
METER_ID_POWER_L3 = 57
METER_ID_POWER = 74  # active power sum, W
METER_ID_ENERGY_IMPORT = 209  # active energy import, kWh
METER_ID_ENERGY_EXPORT = 211  # active energy export, kWh
METER_ID_POWER_FACTOR = 356
METER_ID_FREQUENCY = 364

# DC fault reset password required by the firmware.
DC_FAULT_RESET_PASSWORD = 0xDC42FA23

# API topics
T_INFO_NAME = "info/name"
T_INFO_VERSION = "info/version"
T_INFO_DISPLAY_NAME = "info/display_name"
T_INFO_FEATURES = "info/features"
T_KEEP_ALIVE = "info/keep_alive"
T_CHARGE_MODE = "power_manager/charge_mode"
T_SUPPORTED_MODES = "charge_manager/supported_charge_modes"
T_PM_CONFIG = "power_manager/config"
T_PM_LOW_LEVEL = "power_manager/low_level_state"
T_EVSE_STATE = "evse/state"
T_EVSE_LOW_LEVEL = "evse/low_level_state"
T_EXTERNAL_ENABLED = "evse/external_enabled"
T_EXTERNAL_CURRENT = "evse/external_current"
T_AUTO_START = "evse/auto_start_charging"
T_BOOST_MODE = "evse/boost_mode"
T_EV_WAKEUP = "evse/ev_wakeup"
T_BUTTON_STATE = "evse/button_state"
T_START_CHARGING = "evse/start_charging"
T_STOP_CHARGING = "evse/stop_charging"
T_RESET_DC_FAULT = "evse/reset_dc_fault_current_state"
T_METER_IDS = "meters/0/value_ids"
T_METER_VALUES = "meters/0/values"
T_CURRENT_CHARGE = "charge_tracker/current_charge"
T_LAST_CHARGES = "charge_tracker/last_charges"
T_EV_STATE = "ev/state"
T_EV_INJECT_SOC = "ev/inject_soc"
T_LIMITS_STATE = "charge_limits/state"
T_LIMITS_DEFAULT = "charge_limits/default_limits"
T_LIMITS_ACTIVE = "charge_limits/active_limits"
T_LIMITS_OVERRIDE_DURATION = "charge_limits/override_duration"
T_LIMITS_OVERRIDE_ENERGY = "charge_limits/override_energy"
T_LIMITS_OVERRIDE_SOC = "charge_limits/override_soc"
T_USERS_CONFIG = "users/config"
T_NFC_SEEN_TAGS = "nfc/seen_tags"
T_NFC_INJECT = "nfc/inject_tag"
T_NFC_INJECT_START = "nfc/inject_tag_start"
T_NFC_INJECT_STOP = "nfc/inject_tag_stop"
T_WIFI_STATE = "wifi/state"
T_ETHERNET_STATE = "ethernet/state"
T_NTP_STATE = "ntp/state"
T_FW_STATE = "firmware_update/state"
T_FW_INSTALL_STATE = "firmware_update/install_state"
T_FW_CHECK = "firmware_update/check_for_update"
T_FW_INSTALL = "firmware_update/install_firmware"
T_REBOOT = "reboot"

# Topics polled every cycle (fallback path) / required for availability.
POLL_FAST: tuple[str, ...] = (
    T_CHARGE_MODE,
    T_SUPPORTED_MODES,
    T_EVSE_STATE,
    T_EXTERNAL_CURRENT,
    T_METER_VALUES,
    T_CURRENT_CHARGE,
    T_EV_STATE,
)
POLL_MEDIUM: tuple[str, ...] = (
    T_EVSE_LOW_LEVEL,
    T_PM_LOW_LEVEL,
    T_LIMITS_STATE,
    T_LIMITS_ACTIVE,
    T_BUTTON_STATE,
    T_NFC_SEEN_TAGS,
    T_FW_INSTALL_STATE,
)
POLL_SLOW: tuple[str, ...] = (
    T_EXTERNAL_ENABLED,
    T_AUTO_START,
    T_BOOST_MODE,
    T_EV_WAKEUP,
    T_PM_CONFIG,
    T_LIMITS_DEFAULT,
    T_LAST_CHARGES,
    T_USERS_CONFIG,
    T_WIFI_STATE,
    T_ETHERNET_STATE,
    T_NTP_STATE,
    T_FW_STATE,
    T_INFO_FEATURES,
)
REQUIRED_TOPICS: tuple[str, ...] = (T_CHARGE_MODE, T_EVSE_STATE)
ALL_TOPICS: frozenset[str] = frozenset((*POLL_FAST, *POLL_MEDIUM, *POLL_SLOW, T_METER_IDS))
