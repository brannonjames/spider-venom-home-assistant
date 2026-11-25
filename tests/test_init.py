"""Tests for Spider Grills Venom setup, unload, and service calls."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.spider_venom.api import SpiderVenomApiError
from custom_components.spider_venom.const import (
    ATTR_TEMPERATURE,
    CONF_THING_NAME,
    DOMAIN,
    SERVICE_SET_TARGET_TEMPERATURE,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from .conftest import MOCK_ENTRY_DATA, MOCK_THING_NAME, SAMPLE_SHADOW


async def test_setup_unload_and_service_lifecycle(hass: HomeAssistant) -> None:
    """Verify service is registered on setup and removed when last entry unloads."""
    entry = MockConfigEntry(domain=DOMAIN, data=MOCK_ENTRY_DATA, unique_id=MOCK_THING_NAME)
    entry.add_to_hass(hass)

    with patch(
        "custom_components.spider_venom.api.SpiderVenomClient.async_get_shadow",
        return_value=SAMPLE_SHADOW,
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert hass.services.has_service(DOMAIN, SERVICE_SET_TARGET_TEMPERATURE)

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()

    assert not hass.services.has_service(DOMAIN, SERVICE_SET_TARGET_TEMPERATURE)


async def test_set_target_temperature_service_single_and_multi(hass: HomeAssistant) -> None:
    """Verify set_target_temperature routing for single and multiple Venoms."""
    entry1 = MockConfigEntry(
        domain=DOMAIN,
        data=MOCK_ENTRY_DATA,
        unique_id=MOCK_THING_NAME,
    )
    entry1.add_to_hass(hass)

    with (
        patch(
            "custom_components.spider_venom.api.SpiderVenomClient.async_get_shadow",
            return_value=SAMPLE_SHADOW,
        ),
        patch(
            "custom_components.spider_venom.api.SpiderVenomClient.async_set_target_temperature",
            new_callable=AsyncMock,
            return_value={},
        ) as mock_set_temp,
    ):
        assert await hass.config_entries.async_setup(entry1.entry_id)
        await hass.async_block_till_done()

        # Single Venom works without thing_name
        await hass.services.async_call(
            DOMAIN,
            SERVICE_SET_TARGET_TEMPERATURE,
            {ATTR_TEMPERATURE: 275},
            blocking=True,
        )
        mock_set_temp.assert_called_once_with(275)

        # Unknown thing_name fails
        with pytest.raises(HomeAssistantError, match="No configured Venom thing named"):
            await hass.services.async_call(
                DOMAIN,
                SERVICE_SET_TARGET_TEMPERATURE,
                {ATTR_TEMPERATURE: 275, CONF_THING_NAME: "does-not-exist"},
                blocking=True,
            )

        # Add a second Venom
        entry2_data = dict(MOCK_ENTRY_DATA, **{CONF_THING_NAME: "venom-test-002"})
        entry2 = MockConfigEntry(
            domain=DOMAIN,
            data=entry2_data,
            unique_id="venom-test-002",
        )
        entry2.add_to_hass(hass)
        assert await hass.config_entries.async_setup(entry2.entry_id)
        await hass.async_block_till_done()

        # Multiple Venoms require thing_name
        with pytest.raises(HomeAssistantError, match="multiple Venoms"):
            await hass.services.async_call(
                DOMAIN,
                SERVICE_SET_TARGET_TEMPERATURE,
                {ATTR_TEMPERATURE: 300},
                blocking=True,
            )

        # Specifying thing_name succeeds
        mock_set_temp.reset_mock()
        await hass.services.async_call(
            DOMAIN,
            SERVICE_SET_TARGET_TEMPERATURE,
            {ATTR_TEMPERATURE: 300, CONF_THING_NAME: "venom-test-002"},
            blocking=True,
        )
        mock_set_temp.assert_called_once_with(300)

        # API error converts to HomeAssistantError
        mock_set_temp.side_effect = SpiderVenomApiError("boom")
        with pytest.raises(HomeAssistantError, match="Unable to set Venom target temperature"):
            await hass.services.async_call(
                DOMAIN,
                SERVICE_SET_TARGET_TEMPERATURE,
                {ATTR_TEMPERATURE: 310, CONF_THING_NAME: "venom-test-002"},
                blocking=True,
            )
