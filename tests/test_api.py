"""Tests for Spider Grills Venom API client."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
from typing import Any
from unittest.mock import MagicMock

from aiohttp import ClientConnectorError
import pytest

from custom_components.spider_venom.api import (
    SpiderGrillsAccountClient,
    SpiderVenomApiError,
    SpiderVenomClient,
    _Credentials,
    _redacted_body,
)


class MockResponse:
    """Minimal async HTTP response mock."""

    def __init__(self, status: int, body: str) -> None:
        self.status = status
        self._body = body

    async def text(self) -> str:
        return self._body

    async def __aenter__(self) -> MockResponse:
        return self

    async def __aexit__(self, *args: Any) -> None:
        return None


def _make_client(session: MagicMock | None = None, thing_name: str = "venom-123") -> SpiderVenomClient:
    return SpiderVenomClient(
        session=session or MagicMock(),
        endpoint="https://example-ats.iot.us-east-2.amazonaws.com/",
        identity_pool_id="us-east-2:11111111-2222-3333-4444-555555555555",
        region="us-east-2",
        thing_name=thing_name,
    )


def test_signed_headers_and_signing_key() -> None:
    """Verify SigV4 headers and key derivation are deterministic."""
    client = _make_client()
    creds = _Credentials(
        access_key_id="AKIAEXAMPLE",
        secret_key="secret-key-value",
        session_token="session-token-value",
        expiration=datetime.now(UTC) + timedelta(hours=1),
        identity_id="us-east-2:id-1",
    )

    headers = client._signed_headers(
        method="GET",
        path="/things/venom-123/shadow",
        query_string="",
        payload="",
        credentials=creds,
        service="iotdata",
    )

    assert headers["x-amz-security-token"] == "session-token-value"
    assert "x-amz-date" in headers
    assert headers["Authorization"].startswith("AWS4-HMAC-SHA256 Credential=AKIAEXAMPLE/")
    assert "SignedHeaders=host;x-amz-date;x-amz-security-token" in headers["Authorization"]
    assert "Signature=" in headers["Authorization"]

    key1 = client._signing_key("secret-key-value", "20260725", "iotdata")
    key2 = client._signing_key("secret-key-value", "20260725", "iotdata")
    assert key1 == key2
    assert len(key1) == 32


async def test_get_shadow_fetches_and_caches_cognito_credentials() -> None:
    """Verify Cognito credentials are fetched once and cached for subsequent requests."""
    session = MagicMock()
    future_exp = (datetime.now(UTC) + timedelta(hours=1)).timestamp()
    session.post.side_effect = [
        MockResponse(200, json.dumps({"IdentityId": "us-east-2:abc"})),
        MockResponse(
            200,
            json.dumps(
                {
                    "Credentials": {
                        "AccessKeyId": "AKIA1",
                        "SecretKey": "SEC1",
                        "SessionToken": "TOK1",
                        "Expiration": future_exp,
                    }
                }
            ),
        ),
    ]
    shadow_payload = {"state": {"reported": {"mainTemp": 225}}}
    session.request.side_effect = [
        MockResponse(200, json.dumps(shadow_payload)),
        MockResponse(200, json.dumps(shadow_payload)),
    ]

    client = _make_client(session)
    first = await client.async_get_shadow()
    second = await client.async_get_shadow()

    assert first == shadow_payload
    assert second == shadow_payload
    assert session.post.call_count == 2
    assert session.request.call_count == 2


async def test_set_target_temperature_posts_desired_payload() -> None:
    """Verify set_target_temperature sends the expected desired shadow JSON."""
    session = MagicMock()
    expected_payload = {"state": {"desired": {"heat": {"t2": {"trgt": 300}}}}}
    session.request.return_value = MockResponse(200, json.dumps(expected_payload))

    client = _make_client(session)
    client._credentials = _Credentials(
        access_key_id="AKIA1",
        secret_key="SEC1",
        session_token="TOK1",
        expiration=datetime.now(UTC) + timedelta(hours=1),
        identity_id="us-east-2:abc",
    )

    await client.async_set_target_temperature(300)

    call = session.request.call_args
    assert call.args[0] == "POST"
    assert call.kwargs["data"] == '{"state":{"desired":{"heat":{"t2":{"trgt":300}}}}}'
    assert call.kwargs["headers"]["Content-Type"] == "application/json"


async def test_iot_shadow_errors_raise_api_error() -> None:
    """Verify HTTP error, invalid JSON, and connection errors raise SpiderVenomApiError."""
    session = MagicMock()
    client = _make_client(session)
    client._credentials = _Credentials(
        access_key_id="AKIA1",
        secret_key="SEC1",
        session_token="TOK1",
        expiration=datetime.now(UTC) + timedelta(hours=1),
        identity_id="us-east-2:abc",
    )

    session.request.return_value = MockResponse(500, "server error")
    with pytest.raises(SpiderVenomApiError, match="HTTP 500"):
        await client.async_get_shadow()

    session.request.return_value = MockResponse(200, "not-json")
    with pytest.raises(SpiderVenomApiError, match="not JSON"):
        await client.async_get_shadow()

    session.request.side_effect = ClientConnectorError(MagicMock(), OSError("refused"))
    with pytest.raises(SpiderVenomApiError, match="could not connect"):
        await client.async_get_shadow()


async def test_account_client_login_and_get_devices() -> None:
    """Verify SpiderGrillsAccountClient login and device list shape handling."""
    session = MagicMock()
    account = SpiderGrillsAccountClient(session=session)

    session.request.return_value = MockResponse(200, json.dumps({"accessToken": "tok-123"}))
    assert await account.async_login(email="user@example.com", password="pw") == "tok-123"

    session.request.return_value = MockResponse(200, json.dumps({}))
    with pytest.raises(SpiderVenomApiError, match="access token"):
        await account.async_login(email="user@example.com", password="pw")

    session.request.return_value = MockResponse(401, json.dumps({"message": "Unauthorized"}))
    with pytest.raises(SpiderVenomApiError, match="HTTP 401"):
        await account.async_login(email="user@example.com", password="pw")

    for payload in (
        [{"thingName": "v1"}],
        {"data": [{"thingName": "v1"}]},
        {"devices": [{"thingName": "v1"}]},
    ):
        session.request.return_value = MockResponse(200, json.dumps(payload))
        devices = await account.async_get_devices("tok-123")
        assert devices == [{"thingName": "v1"}]

    session.request.return_value = MockResponse(200, json.dumps({"unexpected": True}))
    with pytest.raises(SpiderVenomApiError, match="unexpected shape"):
        await account.async_get_devices("tok-123")


def test_redacted_body_masks_sensitive_fields() -> None:
    """Verify sensitive JSON keys are masked by _redacted_body."""
    raw = json.dumps(
        {
            "accessToken": "secret-access",
            "refreshToken": "secret-refresh",
            "password": "secret-password",
            "Credentials": {
                "AccessKeyId": "AKIASECRET",
                "SecretKey": "SECRETKEY",
                "SessionToken": "SESSIONTOK",
            },
            "device": {"thingName": "venom-1"},
        }
    )
    redacted = json.loads(_redacted_body(raw))

    assert redacted["accessToken"] == "***REDACTED***"
    assert redacted["refreshToken"] == "***REDACTED***"
    assert redacted["password"] == "***REDACTED***"
    assert redacted["Credentials"]["AccessKeyId"] == "***REDACTED***"
    assert redacted["Credentials"]["SecretKey"] == "***REDACTED***"
    assert redacted["Credentials"]["SessionToken"] == "***REDACTED***"
    assert redacted["device"]["thingName"] == "venom-1"
