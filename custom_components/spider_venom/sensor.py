"""Sensor entities for Spider Grills Venom."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorEntityDescription, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfTemperature
from homeassistant.const import SIGNAL_STRENGTH_DECIBELS_MILLIWATT as DBM
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import SpiderVenomDataUpdateCoordinator
from .entity import SpiderVenomEntity, value_at_path


@dataclass(frozen=True, kw_only=True)
class SpiderVenomSensorDescription(SensorEntityDescription):
    """Description of a Spider Grills Venom sensor."""

    value_fn: Callable[[dict[str, Any]], Any]


def _path(path: tuple[str, ...]) -> Callable[[dict[str, Any]], Any]:
    return lambda reported: value_at_path(reported, path)


def _timestamp(path: tuple[str, ...]) -> Callable[[dict[str, Any]], Any]:
    def timestamp_value(reported: dict[str, Any]) -> datetime | None:
        value = value_at_path(reported, path)
        if not isinstance(value, int | float) or value <= 0:
            return None
        return datetime.fromtimestamp(value, UTC)

    return timestamp_value


def _errors(reported: dict[str, Any]) -> str | None:
    errors = reported.get("errors")
    if not isinstance(errors, list):
        return None
    return ",".join(str(error) for error in errors)


SENSORS: tuple[SpiderVenomSensorDescription, ...] = (
    SpiderVenomSensorDescription(
        key="model",
        name="Model",
        value_fn=_path(("model",)),
    ),
    SpiderVenomSensorDescription(
        key="firmware_version",
        name="Firmware version",
        value_fn=_path(("vers",)),
    ),
    SpiderVenomSensorDescription(
        key="mac_address",
        name="MAC address",
        value_fn=_path(("mac",)),
    ),
    SpiderVenomSensorDescription(
        key="main_temp",
        name="Current temperature",
        native_unit_of_measurement=UnitOfTemperature.FAHRENHEIT,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_path(("mainTemp",)),
    ),
    SpiderVenomSensorDescription(
        key="target_temp",
        name="Target temperature",
        native_unit_of_measurement=UnitOfTemperature.FAHRENHEIT,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_path(("heat", "t2", "trgt")),
    ),
    SpiderVenomSensorDescription(
        key="target_min",
        name="Minimum target temperature",
        native_unit_of_measurement=UnitOfTemperature.FAHRENHEIT,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_path(("heat", "t2", "min")),
    ),
    SpiderVenomSensorDescription(
        key="target_max",
        name="Maximum target temperature",
        native_unit_of_measurement=UnitOfTemperature.FAHRENHEIT,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_path(("heat", "t2", "max")),
    ),
    SpiderVenomSensorDescription(
        key="heat_intensity",
        name="Heat intensity",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_path(("heat", "t2", "intensity")),
    ),
    SpiderVenomSensorDescription(
        key="heat_start_time",
        name="Heat start time",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=_timestamp(("heat", "t2", "startTime")),
    ),
    SpiderVenomSensorDescription(
        key="high_temp_limit",
        name="High temperature notification limit",
        native_unit_of_measurement=UnitOfTemperature.FAHRENHEIT,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_path(("heat", "t2", "high_limit")),
    ),
    SpiderVenomSensorDescription(
        key="low_temp_limit",
        name="Low temperature notification limit",
        native_unit_of_measurement=UnitOfTemperature.FAHRENHEIT,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_path(("heat", "t2", "low_limit")),
    ),
    SpiderVenomSensorDescription(
        key="rssi",
        name="Signal strength",
        native_unit_of_measurement=DBM,
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_path(("RSSI",)),
    ),
    SpiderVenomSensorDescription(
        key="ssid",
        name="Wi-Fi SSID",
        value_fn=_path(("ssid",)),
    ),
    SpiderVenomSensorDescription(
        key="bssid",
        name="Wi-Fi BSSID",
        value_fn=_path(("bssid",)),
    ),
    SpiderVenomSensorDescription(
        key="update_flag",
        name="Update flag",
        value_fn=_path(("update",)),
    ),
    SpiderVenomSensorDescription(
        key="trigger_flag",
        name="Trigger flag",
        value_fn=_path(("trigger",)),
    ),
    SpiderVenomSensorDescription(
        key="errors",
        name="Errors",
        value_fn=_errors,
    ),
    SpiderVenomSensorDescription(
        key="probe_1_temp",
        name="Probe 1 temperature",
        native_unit_of_measurement=UnitOfTemperature.FAHRENHEIT,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_path(("probes", "p1", "temp")),
    ),
    SpiderVenomSensorDescription(
        key="probe_1_target",
        name="Probe 1 target",
        native_unit_of_measurement=UnitOfTemperature.FAHRENHEIT,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_path(("probes", "p1", "trgt")),
    ),
    SpiderVenomSensorDescription(
        key="probe_2_temp",
        name="Probe 2 temperature",
        native_unit_of_measurement=UnitOfTemperature.FAHRENHEIT,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_path(("probes", "p2", "temp")),
    ),
    SpiderVenomSensorDescription(
        key="probe_2_target",
        name="Probe 2 target",
        native_unit_of_measurement=UnitOfTemperature.FAHRENHEIT,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_path(("probes", "p2", "trgt")),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Spider Grills Venom sensors."""
    coordinator: SpiderVenomDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(SpiderVenomSensor(coordinator, entry, description) for description in SENSORS)


class SpiderVenomSensor(SpiderVenomEntity, SensorEntity):
    """Spider Grills Venom sensor."""

    entity_description: SpiderVenomSensorDescription

    def __init__(
        self,
        coordinator: SpiderVenomDataUpdateCoordinator,
        entry: ConfigEntry,
        description: SpiderVenomSensorDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> Any:
        """Return the sensor value."""
        return self.entity_description.value_fn(self.coordinator.reported)
