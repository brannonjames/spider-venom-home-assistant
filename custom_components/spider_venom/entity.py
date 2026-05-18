"""Base entities for Spider Grills Venom."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_THING_NAME, DOMAIN
from .coordinator import SpiderVenomDataUpdateCoordinator


class SpiderVenomEntity(CoordinatorEntity[SpiderVenomDataUpdateCoordinator]):
    """Base Spider Grills Venom entity."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: SpiderVenomDataUpdateCoordinator,
        entry: ConfigEntry,
        key: str,
    ) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self._thing_name = entry.data[CONF_THING_NAME]
        self._attr_unique_id = f"{self._thing_name}_{key}"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device registry information."""
        reported = self.coordinator.reported
        return DeviceInfo(
            identifiers={(DOMAIN, self._thing_name)},
            manufacturer="Spider Grills",
            model=str(reported.get("model", "Venom")),
            name="Venom",
            sw_version=str(reported.get("vers")) if reported.get("vers") else None,
        )


def value_at_path(data: dict[str, Any], path: tuple[str, ...]) -> Any:
    """Return a nested value from a dict."""
    value: Any = data
    for key in path:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value
