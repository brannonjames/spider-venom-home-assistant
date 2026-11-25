"""Number entities for Spider Grills Venom."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntity,
    NumberEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import SpiderVenomApiError
from .const import (
    DOMAIN,
    MAX_TARGET_TEMPERATURE,
    MIN_TARGET_TEMPERATURE,
)
from .coordinator import SpiderVenomDataUpdateCoordinator
from .entity import SpiderVenomEntity, value_at_path


@dataclass(frozen=True, kw_only=True)
class SpiderVenomNumberDescription(NumberEntityDescription):
    """Description of a Spider Grills Venom number control."""

    reported_path: tuple[str, ...]
    desired_fn: Callable[[int], dict[str, Any]]


NUMBERS: tuple[SpiderVenomNumberDescription, ...] = (
    SpiderVenomNumberDescription(
        key="target_temperature_control",
        name="Target temperature control",
        device_class=NumberDeviceClass.TEMPERATURE,
        native_min_value=MIN_TARGET_TEMPERATURE,
        native_max_value=MAX_TARGET_TEMPERATURE,
        native_step=1,
        native_unit_of_measurement=UnitOfTemperature.FAHRENHEIT,
        reported_path=("heat", "t2", "trgt"),
        desired_fn=lambda value: {"heat": {"t2": {"trgt": value}}},
    ),
    SpiderVenomNumberDescription(
        key="probe_1_target_temperature_control",
        name="Probe 1 target temperature control",
        device_class=NumberDeviceClass.TEMPERATURE,
        native_min_value=0,
        native_max_value=MAX_TARGET_TEMPERATURE,
        native_step=1,
        native_unit_of_measurement=UnitOfTemperature.FAHRENHEIT,
        reported_path=("probes", "p1", "trgt"),
        desired_fn=lambda value: {"probes": {"p1": {"trgt": value}}},
    ),
    SpiderVenomNumberDescription(
        key="probe_2_target_temperature_control",
        name="Probe 2 target temperature control",
        device_class=NumberDeviceClass.TEMPERATURE,
        native_min_value=0,
        native_max_value=MAX_TARGET_TEMPERATURE,
        native_step=1,
        native_unit_of_measurement=UnitOfTemperature.FAHRENHEIT,
        reported_path=("probes", "p2", "trgt"),
        desired_fn=lambda value: {"probes": {"p2": {"trgt": value}}},
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Spider Grills Venom number entities."""
    coordinator: SpiderVenomDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        SpiderVenomTargetTemperatureNumber(coordinator, entry, description)
        for description in NUMBERS
    )


class SpiderVenomTargetTemperatureNumber(SpiderVenomEntity, NumberEntity):
    """Target temperature number control for a Spider Grills Venom."""

    entity_description: SpiderVenomNumberDescription

    def __init__(
        self,
        coordinator: SpiderVenomDataUpdateCoordinator,
        entry: ConfigEntry,
        description: SpiderVenomNumberDescription,
    ) -> None:
        """Initialize the number entity."""
        super().__init__(coordinator, entry, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> Any:
        """Return the current target temperature."""
        is_optimistic, optimistic_value = self.coordinator.get_optimistic_value(
            self.entity_description.reported_path
        )
        if is_optimistic:
            return optimistic_value
        return value_at_path(
            self.coordinator.reported,
            self.entity_description.reported_path,
        )

    async def async_set_native_value(self, value: float) -> None:
        """Set the target temperature."""
        temperature = int(round(value))
        minimum = self.entity_description.native_min_value
        maximum = self.entity_description.native_max_value
        if (minimum is not None and temperature < minimum) or (
            maximum is not None and temperature > maximum
        ):
            raise HomeAssistantError(
                f"{self.entity_description.name} must be between "
                f"{minimum:g} and {maximum:g} F"
            )

        try:
            await self.coordinator.client.async_update_desired(
                self.entity_description.desired_fn(temperature)
            )
        except SpiderVenomApiError as err:
            raise HomeAssistantError(
                f"Unable to set {self.entity_description.name}: {err}"
            ) from err

        self.coordinator.set_optimistic_value(
            self.entity_description.reported_path,
            temperature,
        )
        await self.coordinator.async_request_refresh()
