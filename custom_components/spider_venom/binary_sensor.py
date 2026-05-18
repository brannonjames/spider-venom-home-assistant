"""Binary sensor entities for Spider Grills Venom."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import SpiderVenomDataUpdateCoordinator
from .entity import SpiderVenomEntity, value_at_path


@dataclass(frozen=True, kw_only=True)
class SpiderVenomBinarySensorDescription(BinarySensorEntityDescription):
    """Description of a Spider Grills Venom binary sensor."""

    value_fn: Callable[[dict[str, Any]], Any]


def _path(path: tuple[str, ...]) -> Callable[[dict[str, Any]], Any]:
    return lambda reported: value_at_path(reported, path)


BINARY_SENSORS: tuple[SpiderVenomBinarySensorDescription, ...] = (
    SpiderVenomBinarySensorDescription(
        key="power",
        name="Power",
        device_class=BinarySensorDeviceClass.POWER,
        value_fn=_path(("pwrOn",)),
    ),
    SpiderVenomBinarySensorDescription(
        key="engaged",
        name="Engaged",
        value_fn=_path(("engaged",)),
    ),
    SpiderVenomBinarySensorDescription(
        key="paused",
        name="Paused",
        value_fn=_path(("paused",)),
    ),
    SpiderVenomBinarySensorDescription(
        key="door",
        name="Door",
        device_class=BinarySensorDeviceClass.DOOR,
        value_fn=_path(("doorOpn",)),
    ),
    SpiderVenomBinarySensorDescription(
        key="heating",
        name="Heating",
        device_class=BinarySensorDeviceClass.HEAT,
        value_fn=_path(("heat", "t2", "heating")),
    ),
    SpiderVenomBinarySensorDescription(
        key="fahrenheit_mode",
        name="Fahrenheit mode",
        value_fn=_path(("fah",)),
    ),
    SpiderVenomBinarySensorDescription(
        key="high_temp_enabled",
        name="High temperature mode",
        value_fn=_path(("heat", "t2", "highTemp_enable")),
    ),
    SpiderVenomBinarySensorDescription(
        key="high_temp_notification",
        name="High temperature notification",
        device_class=BinarySensorDeviceClass.PROBLEM,
        value_fn=_path(("notifications", "high_temp")),
    ),
    SpiderVenomBinarySensorDescription(
        key="low_temp_notification",
        name="Low temperature notification",
        device_class=BinarySensorDeviceClass.PROBLEM,
        value_fn=_path(("notifications", "low_temp")),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Spider Grills Venom binary sensors."""
    coordinator: SpiderVenomDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        SpiderVenomBinarySensor(coordinator, entry, description)
        for description in BINARY_SENSORS
    )


class SpiderVenomBinarySensor(SpiderVenomEntity, BinarySensorEntity):
    """Spider Grills Venom binary sensor."""

    entity_description: SpiderVenomBinarySensorDescription

    def __init__(
        self,
        coordinator: SpiderVenomDataUpdateCoordinator,
        entry: ConfigEntry,
        description: SpiderVenomBinarySensorDescription,
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator, entry, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool | None:
        """Return the binary sensor state."""
        value = self.entity_description.value_fn(self.coordinator.reported)
        return bool(value) if value is not None else None
