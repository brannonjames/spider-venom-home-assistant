"""Spider Grills Venom integration."""

from __future__ import annotations

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import SpiderVenomApiError, SpiderVenomClient
from .const import (
    ATTR_TEMPERATURE,
    CONF_ENDPOINT,
    CONF_IDENTITY_POOL_ID,
    CONF_REGION,
    CONF_THING_NAME,
    DOMAIN,
    MAX_TARGET_TEMPERATURE,
    MIN_TARGET_TEMPERATURE,
    PLATFORMS,
    SERVICE_SET_TARGET_TEMPERATURE,
)
from .coordinator import SpiderVenomDataUpdateCoordinator

SET_TARGET_TEMPERATURE_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_TEMPERATURE): vol.All(
            vol.Coerce(int),
            vol.Range(min=MIN_TARGET_TEMPERATURE, max=MAX_TARGET_TEMPERATURE),
        ),
        vol.Optional(CONF_THING_NAME): str,
    }
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Spider Grills Venom from a config entry."""
    client = SpiderVenomClient(
        session=async_get_clientsession(hass),
        endpoint=entry.data[CONF_ENDPOINT],
        identity_pool_id=entry.data[CONF_IDENTITY_POOL_ID],
        region=entry.data[CONF_REGION],
        thing_name=entry.data[CONF_THING_NAME],
    )
    coordinator = SpiderVenomDataUpdateCoordinator(hass, client, entry)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    _async_register_services(hass)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id)
        if not hass.data[DOMAIN]:
            hass.services.async_remove(DOMAIN, SERVICE_SET_TARGET_TEMPERATURE)
    return unloaded


def _async_register_services(hass: HomeAssistant) -> None:
    """Register Spider Grills Venom services."""
    if hass.services.has_service(DOMAIN, SERVICE_SET_TARGET_TEMPERATURE):
        return

    async def async_set_target_temperature(call: ServiceCall) -> None:
        coordinators: dict[str, SpiderVenomDataUpdateCoordinator] = hass.data.get(DOMAIN, {})
        thing_name = call.data.get(CONF_THING_NAME)
        temperature = call.data[ATTR_TEMPERATURE]

        if thing_name is not None:
            coordinator = next(
                (
                    candidate
                    for candidate in coordinators.values()
                    if candidate.entry.data[CONF_THING_NAME] == thing_name.strip()
                ),
                None,
            )
            if coordinator is None:
                raise HomeAssistantError(f"No configured Venom thing named {thing_name}")
        elif len(coordinators) == 1:
            coordinator = next(iter(coordinators.values()))
        else:
            raise HomeAssistantError("thing_name is required when multiple Venoms are configured")

        try:
            await coordinator.client.async_set_target_temperature(temperature)
        except SpiderVenomApiError as err:
            raise HomeAssistantError(f"Unable to set Venom target temperature: {err}") from err

        await coordinator.async_request_refresh()

    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_TARGET_TEMPERATURE,
        async_set_target_temperature,
        schema=SET_TARGET_TEMPERATURE_SCHEMA,
    )
