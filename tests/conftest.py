"""Shared fixtures for Spider Grills Venom tests."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

import pytest

from custom_components.spider_venom.const import (
    CONF_ENDPOINT,
    CONF_IDENTITY_POOL_ID,
    CONF_REGION,
    CONF_THING_NAME,
    DEFAULT_ENDPOINT,
    DEFAULT_IDENTITY_POOL_ID,
    DEFAULT_REGION,
)
from homeassistant.const import CONF_SCAN_INTERVAL

MOCK_THING_NAME = "venom-test-001"

MOCK_ENTRY_DATA: dict[str, Any] = {
    CONF_ENDPOINT: DEFAULT_ENDPOINT,
    CONF_IDENTITY_POOL_ID: DEFAULT_IDENTITY_POOL_ID,
    CONF_REGION: DEFAULT_REGION,
    CONF_THING_NAME: MOCK_THING_NAME,
    CONF_SCAN_INTERVAL: 30,
}

SAMPLE_SHADOW: dict[str, Any] = {
    "state": {
        "reported": {
            "model": "Venom",
            "vers": "1.2.3",
            "mac": "AA:BB:CC:DD:EE:FF",
            "mainTemp": 225,
            "RSSI": -58,
            "ssid": "BackyardWiFi",
            "bssid": "11:22:33:44:55:66",
            "update": 0,
            "trigger": 1,
            "errors": ["E01", "E02"],
            "pwrOn": True,
            "engaged": True,
            "paused": False,
            "doorOpn": False,
            "fah": True,
            "heat": {
                "t2": {
                    "trgt": 250,
                    "min": 150,
                    "max": 550,
                    "intensity": 65,
                    "startTime": 1700000000,
                    "high_limit": 450,
                    "low_limit": 175,
                    "heating": True,
                    "highTemp_enable": False,
                }
            },
            "probes": {
                "p1": {"temp": 145, "trgt": 165},
                "p2": {"temp": 180, "trgt": 203},
            },
            "notifications": {
                "high_temp": False,
                "low_temp": True,
            },
        }
    },
    "timestamp": 1700000123,
}


def make_shadow(**overrides: Any) -> dict[str, Any]:
    """Return a deep copy of the sample shadow."""
    shadow = deepcopy(SAMPLE_SHADOW)
    shadow["state"]["reported"].update(overrides)
    return shadow


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Enable custom integrations in all tests."""
    return
