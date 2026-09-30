"""Event entities for WARP chargers."""

from __future__ import annotations

from typing import Any

from homeassistant.components.event import (
    EventDeviceClass,
    EventEntity,
    EventEntityDescription,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import WarpConfigEntry, WarpData, WarpDataUpdateCoordinator
from .entity import WarpEntity

PARALLEL_UPDATES = 0

EVENT_SEEN = "seen"
EVENT_STARTED = "started"
EVENT_ENDED = "ended"
EVENT_PRESSED = "pressed"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: WarpConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up WARP event entities."""
    coordinator = entry.runtime_data.coordinator
    data = coordinator.data
    entities: list[WarpEventEntity] = []
    if data.has_topic("nfc/seen_tags"):
        entities.append(WarpNfcTagEvent(entry=entry, coordinator=coordinator))
    if data.current_charge is not None:
        entities.append(WarpChargeSessionEvent(entry=entry, coordinator=coordinator))
    if data.button_state:
        entities.append(WarpButtonEvent(entry=entry, coordinator=coordinator))
    async_add_entities(entities)


class WarpEventEntity(WarpEntity, EventEntity):
    """Base class: compares consecutive snapshots and fires events."""

    _primed = False

    def __init__(
        self,
        *,
        entry: WarpConfigEntry,
        coordinator: WarpDataUpdateCoordinator,
        description: EventEntityDescription,
    ) -> None:
        """Initialize and prime with the current snapshot."""
        super().__init__(entry=entry, coordinator=coordinator, description=description)
        self._prime(coordinator.data)
        self._primed = True

    def _prime(self, data: WarpData) -> None:
        """Remember the baseline; overridden."""

    def _detect(self, data: WarpData) -> None:
        """Compare with the baseline and call _trigger_event; overridden."""

    @callback
    def _handle_coordinator_update(self) -> None:
        if self._primed and self.coordinator.data is not None:
            self._detect(self.coordinator.data)
        super()._handle_coordinator_update()


class WarpNfcTagEvent(WarpEventEntity):
    """Fires when an NFC tag is presented."""

    _attr_translation_key = "nfc_tag"
    _attr_event_types = [EVENT_SEEN]

    def __init__(
        self, *, entry: WarpConfigEntry, coordinator: WarpDataUpdateCoordinator
    ) -> None:
        """Initialize."""
        self._last_seen: dict[str, float] = {}
        super().__init__(
            entry=entry,
            coordinator=coordinator,
            description=EventEntityDescription(key="nfc_tag"),
        )

    def _snapshot(self, data: WarpData) -> dict[str, float]:
        return {
            str(t.get("tag_id")): float(t.get("last_seen", 0) or 0)
            for t in data.seen_tags
            if t.get("tag_id")
        }

    def _prime(self, data: WarpData) -> None:
        self._last_seen = self._snapshot(data)

    def _detect(self, data: WarpData) -> None:
        current = self._snapshot(data)
        fired = False
        for tag in data.seen_tags:
            tag_id = str(tag.get("tag_id") or "")
            if not tag_id:
                continue
            now_seen = current[tag_id]
            before = self._last_seen.get(tag_id)
            # `last_seen` counts milliseconds since the tag was presented; a
            # smaller value than before (or a new tag) means a new presentation.
            if before is None or now_seen < before:
                if not fired:
                    self._trigger_event(
                        EVENT_SEEN,
                        {
                            "tag_id": tag_id,
                            "tag_type": tag.get("tag_type"),
                            "user": data.user_name(tag.get("user_id")),
                        },
                    )
                    fired = True
        self._last_seen = current


class WarpChargeSessionEvent(WarpEventEntity):
    """Fires when a charge session starts or ends."""

    _attr_translation_key = "charge_session"
    _attr_event_types = [EVENT_STARTED, EVENT_ENDED]

    def __init__(
        self, *, entry: WarpConfigEntry, coordinator: WarpDataUpdateCoordinator
    ) -> None:
        """Initialize."""
        self._active = False
        self._user: str | None = None
        super().__init__(
            entry=entry,
            coordinator=coordinator,
            description=EventEntityDescription(key="charge_session"),
        )

    def _prime(self, data: WarpData) -> None:
        self._active = data.session_active
        self._user = data.session_user

    def _detect(self, data: WarpData) -> None:
        active = data.session_active
        if active and not self._active:
            self._user = data.session_user
            self._trigger_event(EVENT_STARTED, {"user": self._user})
        elif self._active and not active:
            last = data.last_charge or {}
            attrs: dict[str, Any] = {
                "user": self._user,
                "energy_kwh": last.get("energy_charged"),
                "duration_s": last.get("charge_duration"),
            }
            self._trigger_event(EVENT_ENDED, attrs)
            self._user = None
        self._active = active


class WarpButtonEvent(WarpEventEntity):
    """Fires when the front button is pressed."""

    _attr_translation_key = "button"
    _attr_device_class = EventDeviceClass.BUTTON
    _attr_event_types = [EVENT_PRESSED]

    def __init__(
        self, *, entry: WarpConfigEntry, coordinator: WarpDataUpdateCoordinator
    ) -> None:
        """Initialize."""
        self._press_time: Any = None
        super().__init__(
            entry=entry,
            coordinator=coordinator,
            description=EventEntityDescription(key="button"),
        )

    def _prime(self, data: WarpData) -> None:
        self._press_time = data.button_state.get("button_press_time")

    def _detect(self, data: WarpData) -> None:
        press_time = data.button_state.get("button_press_time")
        if press_time not in (None, 0) and press_time != self._press_time:
            self._trigger_event(EVENT_PRESSED)
        self._press_time = press_time
