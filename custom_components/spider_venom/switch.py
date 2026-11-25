"""Switch entities for Spider Grills Venom."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.switch import SwitchDeviceClass, SwitchEntity, SwitchEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import SpiderVenomApiError
from .const import DOMAIN
from .coordinator import SpiderVenomDataUpdateCoordinator
from .entity import SpiderVenomEntity, value_at_path


@dataclass(frozen=True, kw_only=True)
class SpiderVenomSwitchDescription(SwitchEntityDescription):
    """Description of a Spider Grills Venom switch."""

    reported_path: tuple[str, ...]
    desired_fn: Callable[[bool], dict[str, Any]]


SWITCHES: tuple[SpiderVenomSwitchDescription, ...] = (
    SpiderVenomSwitchDescription(
        key="power_control",
        name="Power control",
        device_class=SwitchDeviceClass.SWITCH,
        reported_path=("pwrOn",),
        desired_fn=lambda value: {"pwrOn": value},
    ),
    SpiderVenomSwitchDescription(
        key="engaged_control",
        name="Engaged control",
        device_class=SwitchDeviceClass.SWITCH,
        reported_path=("engaged",),
        desired_fn=lambda value: {"engaged": value},
    ),
    SpiderVenomSwitchDescription(
        key="paused_control",
        name="Paused control",
        device_class=SwitchDeviceClass.SWITCH,
        reported_path=("paused",),
        desired_fn=lambda value: {"paused": value},
    ),
    SpiderVenomSwitchDescription(
        key="high_temp_mode_control",
        name="High temperature mode control",
        device_class=SwitchDeviceClass.SWITCH,
        reported_path=("heat", "t2", "highTemp_enable"),
        desired_fn=lambda value: {"heat": {"t2": {"highTemp_enable": value}}},
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Spider Grills Venom switches."""
    coordinator: SpiderVenomDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        SpiderVenomSwitch(coordinator, entry, description) for description in SWITCHES
    )


class SpiderVenomSwitch(SpiderVenomEntity, SwitchEntity):
    """Spider Grills Venom switch."""

    entity_description: SpiderVenomSwitchDescription

    def __init__(
        self,
        coordinator: SpiderVenomDataUpdateCoordinator,
        entry: ConfigEntry,
        description: SpiderVenomSwitchDescription,
    ) -> None:
        """Initialize the switch."""
        super().__init__(coordinator, entry, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool | None:
        """Return the switch state."""
        is_optimistic, optimistic_value = self.coordinator.get_optimistic_value(
            self.entity_description.reported_path
        )
        if is_optimistic:
            return bool(optimistic_value)
        value = value_at_path(
            self.coordinator.reported,
            self.entity_description.reported_path,
        )
        return bool(value) if value is not None else None

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on."""
        await self._async_set_value(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off."""
        await self._async_set_value(False)

    async def _async_set_value(self, value: bool) -> None:
        """Write switch state to the desired shadow."""
        try:
            await self.coordinator.client.async_update_desired(
                self.entity_description.desired_fn(value)
            )
        except SpiderVenomApiError as err:
            raise HomeAssistantError(f"Unable to update Venom control: {err}") from err

        self.coordinator.set_optimistic_value(
            self.entity_description.reported_path,
            value,
        )
        await self.coordinator.async_request_refresh()
