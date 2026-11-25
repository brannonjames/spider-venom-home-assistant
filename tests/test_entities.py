"""Tests for Spider Grills Venom entities."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.spider_venom.const import DOMAIN
from custom_components.spider_venom.sensor import _errors, _timestamp
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.util.unit_system import US_CUSTOMARY_SYSTEM

from .conftest import MOCK_ENTRY_DATA, MOCK_THING_NAME, SAMPLE_SHADOW


def _entity_id_by_key(hass: HomeAssistant, platform: str, key: str) -> str:
    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id(platform, DOMAIN, f"{MOCK_THING_NAME}_{key}")
    assert entity_id is not None, f"Missing entity for {platform} {key}"
    return entity_id


async def test_entities_initial_states_and_device_registry(hass: HomeAssistant) -> None:
    """Verify all sensors, binary sensors, numbers, switches, and device info."""
    hass.config.units = US_CUSTOMARY_SYSTEM
    entry = MockConfigEntry(domain=DOMAIN, data=MOCK_ENTRY_DATA, unique_id=MOCK_THING_NAME, title="Patio Venom")
    entry.add_to_hass(hass)

    with patch(
        "custom_components.spider_venom.api.SpiderVenomClient.async_get_shadow",
        return_value=SAMPLE_SHADOW,
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    # Sensors
    assert hass.states.get(_entity_id_by_key(hass, "sensor", "model")).state == "Venom"
    assert hass.states.get(_entity_id_by_key(hass, "sensor", "firmware_version")).state == "1.2.3"
    assert hass.states.get(_entity_id_by_key(hass, "sensor", "mac_address")).state == "AA:BB:CC:DD:EE:FF"
    assert hass.states.get(_entity_id_by_key(hass, "sensor", "main_temp")).state == "225"
    assert hass.states.get(_entity_id_by_key(hass, "sensor", "target_temp")).state == "250"
    assert hass.states.get(_entity_id_by_key(hass, "sensor", "heat_intensity")).state == "65"
    assert hass.states.get(_entity_id_by_key(hass, "sensor", "rssi")).state == "-58"
    assert hass.states.get(_entity_id_by_key(hass, "sensor", "errors")).state == "E01,E02"
    assert hass.states.get(_entity_id_by_key(hass, "sensor", "probe_1_temp")).state == "145"
    assert hass.states.get(_entity_id_by_key(hass, "sensor", "probe_2_temp")).state == "180"

    # Binary sensors
    assert hass.states.get(_entity_id_by_key(hass, "binary_sensor", "power")).state == "on"
    assert hass.states.get(_entity_id_by_key(hass, "binary_sensor", "engaged")).state == "on"
    assert hass.states.get(_entity_id_by_key(hass, "binary_sensor", "paused")).state == "off"
    assert hass.states.get(_entity_id_by_key(hass, "binary_sensor", "door")).state == "off"
    assert hass.states.get(_entity_id_by_key(hass, "binary_sensor", "heating")).state == "on"
    assert hass.states.get(_entity_id_by_key(hass, "binary_sensor", "low_temp_notification")).state == "on"

    # Numbers & switches
    assert hass.states.get(_entity_id_by_key(hass, "number", "target_temperature_control")).state == "250"
    assert hass.states.get(_entity_id_by_key(hass, "number", "probe_1_target_temperature_control")).state == "165"
    assert hass.states.get(_entity_id_by_key(hass, "number", "probe_2_target_temperature_control")).state == "203"
    assert hass.states.get(_entity_id_by_key(hass, "switch", "power_control")).state == "on"
    assert hass.states.get(_entity_id_by_key(hass, "switch", "paused_control")).state == "off"

    # Device registry
    dev_reg = dr.async_get(hass)
    device = dev_reg.async_get_device(identifiers={(DOMAIN, MOCK_THING_NAME)})
    assert device is not None
    assert device.manufacturer == "Spider Grills"
    assert device.model == "Venom"
    assert device.sw_version == "1.2.3"


async def test_number_and_switch_controls(hass: HomeAssistant) -> None:
    """Verify number and switch service calls update desired shadow and optimistic state."""
    hass.config.units = US_CUSTOMARY_SYSTEM
    entry = MockConfigEntry(domain=DOMAIN, data=MOCK_ENTRY_DATA, unique_id=MOCK_THING_NAME)
    entry.add_to_hass(hass)

    with (
        patch(
            "custom_components.spider_venom.api.SpiderVenomClient.async_get_shadow",
            return_value=SAMPLE_SHADOW,
        ),
        patch(
            "custom_components.spider_venom.api.SpiderVenomClient.async_update_desired",
            new_callable=AsyncMock,
            return_value={},
        ) as mock_update,
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        target_entity = _entity_id_by_key(hass, "number", "target_temperature_control")
        await hass.services.async_call(
            "number",
            "set_value",
            {"entity_id": target_entity, "value": 325},
            blocking=True,
        )
        mock_update.assert_any_call({"heat": {"t2": {"trgt": 325}}})
        assert hass.states.get(target_entity).state == "325"

        probe1_entity = _entity_id_by_key(hass, "number", "probe_1_target_temperature_control")
        await hass.services.async_call(
            "number",
            "set_value",
            {"entity_id": probe1_entity, "value": 195},
            blocking=True,
        )
        mock_update.assert_any_call({"probes": {"p1": {"trgt": 195}}})
        assert hass.states.get(probe1_entity).state == "195"

        power_entity = _entity_id_by_key(hass, "switch", "power_control")
        await hass.services.async_call(
            "switch",
            "turn_off",
            {"entity_id": power_entity},
            blocking=True,
        )
        mock_update.assert_any_call({"pwrOn": False})
        assert hass.states.get(power_entity).state == "off"

        paused_entity = _entity_id_by_key(hass, "switch", "paused_control")
        await hass.services.async_call(
            "switch",
            "turn_on",
            {"entity_id": paused_entity},
            blocking=True,
        )
        mock_update.assert_any_call({"paused": True})
        assert hass.states.get(paused_entity).state == "on"


async def test_number_entity_rejects_out_of_range_directly(hass: HomeAssistant) -> None:
    """Verify SpiderVenomTargetTemperatureNumber validates min/max bounds."""
    hass.config.units = US_CUSTOMARY_SYSTEM
    entry = MockConfigEntry(domain=DOMAIN, data=MOCK_ENTRY_DATA, unique_id=MOCK_THING_NAME)
    entry.add_to_hass(hass)

    with patch(
        "custom_components.spider_venom.api.SpiderVenomClient.async_get_shadow",
        return_value=SAMPLE_SHADOW,
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    target_entity = _entity_id_by_key(hass, "number", "target_temperature_control")
    component = hass.data["entity_components"]["number"]
    entity = component.get_entity(target_entity)
    assert entity is not None

    with pytest.raises(HomeAssistantError):
        await entity.async_set_native_value(100)


def test_sensor_helper_functions() -> None:
    """Verify _timestamp and _errors helpers."""
    ts_fn = _timestamp(("heat", "t2", "startTime"))
    assert ts_fn({"heat": {"t2": {"startTime": 1700000000}}}) == datetime.fromtimestamp(1700000000, UTC)
    assert ts_fn({"heat": {"t2": {"startTime": 0}}}) is None
    assert ts_fn({"heat": {"t2": {"startTime": -5}}}) is None
    assert ts_fn({}) is None

    assert _errors({"errors": ["E1", "E2"]}) == "E1,E2"
    assert _errors({"errors": "not-a-list"}) is None
    assert _errors({}) is None
