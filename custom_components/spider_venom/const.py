"""Constants for the Spider Grills Venom integration."""

from __future__ import annotations

from datetime import timedelta

DOMAIN = "spider_venom"

CONF_ENDPOINT = "endpoint"
CONF_IDENTITY_POOL_ID = "identity_pool_id"
CONF_REGION = "region"
CONF_THING_NAME = "thing_name"

ATTR_TEMPERATURE = "temperature"

DEFAULT_ENDPOINT = "a1gzggdqzynf8-ats.iot.us-east-2.amazonaws.com"
DEFAULT_IDENTITY_POOL_ID = "us-east-2:900c6051-7296-4d27-9295-a11f72797d14"
DEFAULT_REGION = "us-east-2"
DEFAULT_SCAN_INTERVAL = timedelta(seconds=30)

MIN_TARGET_TEMPERATURE = 150
MAX_TARGET_TEMPERATURE = 550

PLATFORMS = ["sensor", "binary_sensor", "number", "switch"]

SERVICE_SET_TARGET_TEMPERATURE = "set_target_temperature"
