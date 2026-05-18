"""Switch entities for Spider Grills Venom."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
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

    value_fn: Callable[[dict[str, Any]], Any]
    desired_fn: Callable[[bool], dict[str, Any]]


def _path(path: tuple[str, ...]) -> Callable[[dict[str, Any]], Any]:
    return lambda reported: value_at_path(reported, path)


SWITCHES: tuple[SpiderVenomSwitchDescription, ...] = (
    SpiderVenomSwitchDescription(
        key="power_control",
        name="Power control",
        device_class=SwitchDeviceClass.SWITCH,
        value_fn=_path(("pwrOn",)),
        desired_fn=lambda value: {"pwrOn": value},
    ),
    SpiderVenomSwitchDescription(
        key="engaged_control",
        name="Engaged control",
        device_class=SwitchDeviceClass.SWITCH,
        value_fn=_path(("engaged",)),
        desired_fn=lambda value: {"engaged": value},
    ),
    SpiderVenomSwitchDescription(
        key="paused_control",
        name="Paused control",
        device_class=SwitchDeviceClass.SWITCH,
        value_fn=_path(("paused",)),
        desired_fn=lambda value: {"paused": value},
    ),
    SpiderVenomSwitchDescription(
        key="high_temp_mode_control",
        name="High temperature mode control",
        device_class=SwitchDeviceClass.SWITCH,
        value_fn=_path(("heat", "t2", "highTemp_enable")),
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
    _optimistic_ttl = timedelta(seconds=60)

    def __init__(
        self,
        coordinator: SpiderVenomDataUpdateCoordinator,
        entry: ConfigEntry,
        description: SpiderVenomSwitchDescription,
    ) -> None:
        """Initialize the switch."""
        super().__init__(coordinator, entry, description.key)
        self.entity_description = description
        self._optimistic_value: bool | None = None
        self._optimistic_until: datetime | None = None

    @property
    def is_on(self) -> bool | None:
        """Return the switch state."""
        value = self.entity_description.value_fn(self.coordinator.reported)
        if self._optimistic_value is not None:
            if value == self._optimistic_value or self._optimistic_expired:
                self._optimistic_value = None
                self._optimistic_until = None
            else:
                return self._optimistic_value
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

        self._optimistic_value = value
        self._optimistic_until = datetime.now(UTC) + self._optimistic_ttl
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()

    @property
    def _optimistic_expired(self) -> bool:
        """Return true if the optimistic state should be discarded."""
        return self._optimistic_until is not None and datetime.now(UTC) >= self._optimistic_until
