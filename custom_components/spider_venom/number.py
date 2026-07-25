"""Number entities for Spider Grills Venom."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from homeassistant.components.number import NumberEntity, NumberEntityDescription
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
    _optimistic_ttl = timedelta(seconds=60)

    def __init__(
        self,
        coordinator: SpiderVenomDataUpdateCoordinator,
        entry: ConfigEntry,
        description: SpiderVenomNumberDescription,
    ) -> None:
        """Initialize the number entity."""
        super().__init__(coordinator, entry, description.key)
        self.entity_description = description
        self._optimistic_value: int | None = None
        self._optimistic_until: datetime | None = None

    @property
    def native_value(self) -> Any:
        """Return the current target temperature."""
        reported_value = value_at_path(
            self.coordinator.reported,
            self.entity_description.reported_path,
        )
        if self._optimistic_value is not None:
            if reported_value == self._optimistic_value or self._optimistic_expired:
                self._optimistic_value = None
                self._optimistic_until = None
            else:
                return self._optimistic_value
        return reported_value

    async def async_set_native_value(self, value: float) -> None:
        """Set the target temperature."""
        temperature = int(round(value))
        minimum = self.entity_description.native_min_value
        maximum = self.entity_description.native_max_value
        if temperature < minimum or temperature > maximum:
            raise HomeAssistantError(
                f"{self.entity_description.name} must be between "
                f"{minimum:g} and {maximum:g} F"
            )

        try:
            await self.coordinator.client.async_update_desired(
                self.entity_description.desired_fn(temperature)
            )
        except SpiderVenomApiError as err:
            raise HomeAssistantError(f"Unable to set Venom target temperature: {err}") from err

        self._optimistic_value = temperature
        self._optimistic_until = datetime.now(UTC) + self._optimistic_ttl
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()

    @property
    def _optimistic_expired(self) -> bool:
        """Return true if the optimistic state should be discarded."""
        return self._optimistic_until is not None and datetime.now(UTC) >= self._optimistic_until
