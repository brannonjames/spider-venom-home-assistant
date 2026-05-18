"""Data update coordinator for Spider Grills Venom."""

from __future__ import annotations

from datetime import timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import SpiderVenomApiError, SpiderVenomClient
from .const import DEFAULT_SCAN_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)


class SpiderVenomDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinate Spider Grills Venom shadow polling."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: SpiderVenomClient,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the coordinator."""
        interval_seconds = entry.data.get(CONF_SCAN_INTERVAL)
        interval = (
            timedelta(seconds=interval_seconds)
            if isinstance(interval_seconds, int)
            else DEFAULT_SCAN_INTERVAL
        )
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=interval,
        )
        self.client = client
        self.entry = entry

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from AWS IoT."""
        try:
            return await self.client.async_get_shadow()
        except SpiderVenomApiError as err:
            raise UpdateFailed(str(err)) from err

    @property
    def reported(self) -> dict[str, Any]:
        """Return reported shadow state."""
        data = self.data or {}
        reported = data.get("state", {}).get("reported", {})
        return reported if isinstance(reported, dict) else {}
