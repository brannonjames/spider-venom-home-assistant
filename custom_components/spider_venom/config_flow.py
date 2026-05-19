"""Config flow for Spider Grills Venom."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD, CONF_SCAN_INTERVAL
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import SpiderGrillsAccountClient, SpiderVenomApiError, SpiderVenomClient
from .const import (
    CONF_ENDPOINT,
    CONF_IDENTITY_POOL_ID,
    CONF_REGION,
    CONF_THING_NAME,
    DEFAULT_ENDPOINT,
    DEFAULT_IDENTITY_POOL_ID,
    DEFAULT_REGION,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


class SpiderVenomConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a Spider Grills Venom config flow."""

    VERSION = 1
    _discovered_devices: dict[str, dict[str, Any]]
    _scan_interval: int

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Handle the initial step."""
        return await self.async_step_account(user_input)

    async def async_step_account(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Discover devices with a Spider Grills account."""
        errors: dict[str, str] = {}

        if user_input is not None:
            account_client = SpiderGrillsAccountClient(session=async_get_clientsession(self.hass))
            try:
                access_token = await account_client.async_login(
                    email=user_input[CONF_EMAIL].strip(),
                    password=user_input[CONF_PASSWORD],
                )
                devices = await account_client.async_get_devices(access_token)
            except SpiderVenomApiError as err:
                _LOGGER.warning("Unable to discover Spider Venom devices: %s", err)
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected error discovering Spider Venom devices")
                errors["base"] = "unknown"
            else:
                self._scan_interval = user_input[CONF_SCAN_INTERVAL]
                self._discovered_devices = {
                    thing_name: device
                    for device in devices
                    if (thing_name := _device_thing_name(device)) is not None
                }
                if not self._discovered_devices:
                    errors["base"] = "no_devices"
                else:
                    return await self.async_step_select_device()

        return self.async_show_form(
            step_id="account",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_EMAIL): str,
                    vol.Required(CONF_PASSWORD): str,
                    vol.Optional(
                        CONF_SCAN_INTERVAL,
                        default=int(DEFAULT_SCAN_INTERVAL.total_seconds()),
                    ): vol.All(vol.Coerce(int), vol.Range(min=10, max=3600)),
                }
            ),
            errors=errors,
        )

    async def async_step_select_device(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Select a discovered Spider Grills device."""
        errors: dict[str, str] = {}
        device_options = {
            thing_name: _device_label(device, thing_name)
            for thing_name, device in self._discovered_devices.items()
        }

        if user_input is not None:
            thing_name = user_input[CONF_THING_NAME]
            device = self._discovered_devices[thing_name]
            try:
                return await self._async_create_validated_entry(
                    thing_name=thing_name,
                    endpoint=DEFAULT_ENDPOINT,
                    identity_pool_id=DEFAULT_IDENTITY_POOL_ID,
                    region=DEFAULT_REGION,
                    scan_interval=self._scan_interval,
                    title=_device_label(device, thing_name),
                )
            except SpiderVenomApiError as err:
                _LOGGER.warning("Unable to validate Spider Venom config: %s", err)
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected error validating Spider Venom config")
                errors["base"] = "unknown"

        return self.async_show_form(
            step_id="select_device",
            data_schema=vol.Schema({vol.Required(CONF_THING_NAME): vol.In(device_options)}),
            errors=errors,
        )

    async def _async_create_validated_entry(
        self,
        *,
        thing_name: str,
        endpoint: str,
        identity_pool_id: str,
        region: str,
        scan_interval: int,
        title: str,
    ) -> config_entries.ConfigFlowResult:
        """Validate shadow access and create a config entry."""
        client = SpiderVenomClient(
            session=async_get_clientsession(self.hass),
            endpoint=endpoint,
            identity_pool_id=identity_pool_id,
            region=region,
            thing_name=thing_name,
        )
        await client.async_test_connection()
        await self.async_set_unique_id(thing_name)
        self._abort_if_unique_id_configured()
        return self.async_create_entry(
            title=title,
            data={
                CONF_ENDPOINT: endpoint,
                CONF_IDENTITY_POOL_ID: identity_pool_id,
                CONF_REGION: region,
                CONF_THING_NAME: thing_name,
                CONF_SCAN_INTERVAL: scan_interval,
            },
        )


def _device_thing_name(device: dict[str, Any]) -> str | None:
    """Extract an AWS IoT thing name from a Spider Grills device object."""
    for key in ("thingName", "thing_name", "externalId", "deviceId"):
        value = device.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _device_label(device: dict[str, Any], thing_name: str) -> str:
    """Return a friendly device label."""
    for key in ("deviceName", "name", "model"):
        value = device.get(key)
        if isinstance(value, str) and value:
            return f"{value} ({thing_name})"
    return thing_name
