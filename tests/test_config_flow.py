"""Tests for Spider Grills Venom config flow."""

from __future__ import annotations

from unittest.mock import patch

from custom_components.spider_venom.api import SpiderVenomApiError
from custom_components.spider_venom.config_flow import _device_label, _device_thing_name
from custom_components.spider_venom.const import (
    CONF_ENDPOINT,
    CONF_IDENTITY_POOL_ID,
    CONF_REGION,
    CONF_THING_NAME,
    DOMAIN,
)
from homeassistant import config_entries
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD, CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType


async def test_user_flow_creates_entry_without_storing_credentials(hass: HomeAssistant) -> None:
    """Verify account login -> device selection creates an entry without password or token."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "account"

    with (
        patch(
            "custom_components.spider_venom.config_flow.SpiderGrillsAccountClient.async_login",
            return_value="ephemeral-token",
        ),
        patch(
            "custom_components.spider_venom.config_flow.SpiderGrillsAccountClient.async_get_devices",
            return_value=[{"thingName": "venom-abc", "deviceName": "Patio Grill"}],
        ),
    ):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_EMAIL: " user@example.com ",
                CONF_PASSWORD: "super-secret-password",
                CONF_SCAN_INTERVAL: 45,
            },
        )

    assert result2["type"] is FlowResultType.FORM
    assert result2["step_id"] == "select_device"

    with (
        patch(
            "custom_components.spider_venom.config_flow.SpiderVenomClient.async_test_connection",
            return_value={"state": {"reported": {}}},
        ),
        patch(
            "custom_components.spider_venom.async_setup_entry",
            return_value=True,
        ),
    ):
        result3 = await hass.config_entries.flow.async_configure(
            result2["flow_id"],
            {CONF_THING_NAME: "venom-abc"},
        )

    assert result3["type"] is FlowResultType.CREATE_ENTRY
    assert result3["title"] == "Patio Grill (venom-abc)"
    assert result3["data"][CONF_THING_NAME] == "venom-abc"
    assert result3["data"][CONF_SCAN_INTERVAL] == 45
    assert CONF_ENDPOINT in result3["data"]
    assert CONF_IDENTITY_POOL_ID in result3["data"]
    assert CONF_REGION in result3["data"]
    assert CONF_EMAIL not in result3["data"]
    assert CONF_PASSWORD not in result3["data"]


async def test_account_step_connection_error_and_no_devices(hass: HomeAssistant) -> None:
    """Verify login connection error and empty device list show form errors."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    with patch(
        "custom_components.spider_venom.config_flow.SpiderGrillsAccountClient.async_login",
        side_effect=SpiderVenomApiError("network unreachable"),
    ):
        err_result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_EMAIL: "user@example.com", CONF_PASSWORD: "pw", CONF_SCAN_INTERVAL: 30},
        )
    assert err_result["type"] is FlowResultType.FORM
    assert err_result["errors"] == {"base": "cannot_connect"}

    with (
        patch(
            "custom_components.spider_venom.config_flow.SpiderGrillsAccountClient.async_login",
            return_value="tok",
        ),
        patch(
            "custom_components.spider_venom.config_flow.SpiderGrillsAccountClient.async_get_devices",
            return_value=[{"name": "Missing Thing Name"}],
        ),
    ):
        no_dev_result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_EMAIL: "user@example.com", CONF_PASSWORD: "pw", CONF_SCAN_INTERVAL: 30},
        )
    assert no_dev_result["type"] is FlowResultType.FORM
    assert no_dev_result["errors"] == {"base": "no_devices"}


async def test_select_device_shadow_validation_error(hass: HomeAssistant) -> None:
    """Verify shadow test failure on device selection shows cannot_connect."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    with (
        patch(
            "custom_components.spider_venom.config_flow.SpiderGrillsAccountClient.async_login",
            return_value="tok",
        ),
        patch(
            "custom_components.spider_venom.config_flow.SpiderGrillsAccountClient.async_get_devices",
            return_value=[{"thingName": "venom-abc"}],
        ),
    ):
        step2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_EMAIL: "user@example.com", CONF_PASSWORD: "pw", CONF_SCAN_INTERVAL: 30},
        )

    with patch(
        "custom_components.spider_venom.config_flow.SpiderVenomClient.async_test_connection",
        side_effect=SpiderVenomApiError("IoT shadow request returned HTTP 403"),
    ):
        err_step = await hass.config_entries.flow.async_configure(
            step2["flow_id"],
            {CONF_THING_NAME: "venom-abc"},
        )

    assert err_step["type"] is FlowResultType.FORM
    assert err_step["errors"] == {"base": "cannot_connect"}


def test_device_helpers() -> None:
    """Verify fallback keys in _device_thing_name and _device_label."""
    assert _device_thing_name({"thingName": "t1"}) == "t1"
    assert _device_thing_name({"thing_name": "t2"}) == "t2"
    assert _device_thing_name({"externalId": "t3"}) == "t3"
    assert _device_thing_name({"deviceId": "t4"}) == "t4"
    assert _device_thing_name({}) is None

    assert _device_label({"deviceName": "Grill"}, "t1") == "Grill (t1)"
    assert _device_label({"name": "Kettle"}, "t1") == "Kettle (t1)"
    assert _device_label({"model": "Venom"}, "t1") == "Venom (t1)"
    assert _device_label({}, "t1") == "t1"
