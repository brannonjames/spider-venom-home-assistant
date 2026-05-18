"""Number entities for Spider Grills Venom."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from homeassistant.components.number import NumberEntity
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


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Spider Grills Venom number entities."""
    coordinator: SpiderVenomDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([SpiderVenomTargetTemperatureNumber(coordinator, entry)])


class SpiderVenomTargetTemperatureNumber(SpiderVenomEntity, NumberEntity):
    """Target temperature control for a Spider Grills Venom."""

    _attr_name = "Target temperature control"
    _attr_native_min_value = MIN_TARGET_TEMPERATURE
    _attr_native_max_value = MAX_TARGET_TEMPERATURE
    _attr_native_step = 1
    _attr_native_unit_of_measurement = UnitOfTemperature.FAHRENHEIT
    _optimistic_ttl = timedelta(seconds=60)

    def __init__(
        self,
        coordinator: SpiderVenomDataUpdateCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the number entity."""
        super().__init__(coordinator, entry, "target_temperature_control")
        self._optimistic_value: int | None = None
        self._optimistic_until: datetime | None = None

    @property
    def native_value(self) -> Any:
        """Return the current target temperature."""
        reported_value = value_at_path(self.coordinator.reported, ("heat", "t2", "trgt"))
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
        if temperature < MIN_TARGET_TEMPERATURE or temperature > MAX_TARGET_TEMPERATURE:
            raise HomeAssistantError(
                "Target temperature must be between "
                f"{MIN_TARGET_TEMPERATURE} and {MAX_TARGET_TEMPERATURE} F"
            )

        try:
            await self.coordinator.client.async_set_target_temperature(temperature)
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
