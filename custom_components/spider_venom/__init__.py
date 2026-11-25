"""Spider Grills Venom integration."""

from __future__ import annotations

import voluptuous as vol

from homeassistant.config_entries import ConfigEntryState
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
from .coordinator import SpiderVenomConfigEntry, SpiderVenomDataUpdateCoordinator

SET_TARGET_TEMPERATURE_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_TEMPERATURE): vol.All(
            vol.Coerce(int),
            vol.Range(min=MIN_TARGET_TEMPERATURE, max=MAX_TARGET_TEMPERATURE),
        ),
        vol.Optional(CONF_THING_NAME): str,
    }
)


async def async_setup_entry(hass: HomeAssistant, entry: SpiderVenomConfigEntry) -> bool:
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

    entry.runtime_data = coordinator
    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))
    _async_register_services(hass)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: SpiderVenomConfigEntry) -> bool:
    """Unload a config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        other_loaded = [
            loaded_entry
            for loaded_entry in hass.config_entries.async_entries(DOMAIN)
            if loaded_entry.entry_id != entry.entry_id
            and loaded_entry.state is ConfigEntryState.LOADED
        ]
        if not other_loaded:
            hass.services.async_remove(DOMAIN, SERVICE_SET_TARGET_TEMPERATURE)
    return unloaded


async def _async_reload_entry(hass: HomeAssistant, entry: SpiderVenomConfigEntry) -> None:
    """Reload config entry when options change."""
    await hass.config_entries.async_reload(entry.entry_id)


def _async_register_services(hass: HomeAssistant) -> None:
    """Register Spider Grills Venom services."""
    if hass.services.has_service(DOMAIN, SERVICE_SET_TARGET_TEMPERATURE):
        return

    async def async_set_target_temperature(call: ServiceCall) -> None:
        entries = [
            entry
            for entry in hass.config_entries.async_entries(DOMAIN)
            if entry.state is ConfigEntryState.LOADED
        ]
        thing_name = call.data.get(CONF_THING_NAME)
        temperature = call.data[ATTR_TEMPERATURE]

        if not entries:
            raise HomeAssistantError("No Spider Grills Venom devices are configured")

        if thing_name is not None:
            target_entry = next(
                (
                    candidate
                    for candidate in entries
                    if candidate.data[CONF_THING_NAME] == thing_name.strip()
                ),
                None,
            )
            if target_entry is None:
                raise HomeAssistantError(f"No configured Venom thing named {thing_name}")
        elif len(entries) == 1:
            target_entry = entries[0]
        else:
            raise HomeAssistantError("thing_name is required when multiple Venoms are configured")

        coordinator: SpiderVenomDataUpdateCoordinator = target_entry.runtime_data
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
