"""Client for Spider Grills Venom AWS IoT shadows."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import hashlib
import hmac
import json
import logging
import socket
from typing import Any
from urllib.parse import quote

from aiohttp import ClientConnectorError, ClientError, ClientSession

_LOGGER = logging.getLogger(__name__)
_REDACTED_KEYS = {
    "accesskeyid",
    "accesstoken",
    "authorization",
    "idtoken",
    "password",
    "refreshtoken",
    "secretkey",
    "sessiontoken",
}


class SpiderVenomApiError(Exception):
    """Raised when the Spider Grills cloud API cannot be reached."""


@dataclass(slots=True)
class _Credentials:
    access_key_id: str
    secret_key: str
    session_token: str
    expiration: datetime
    identity_id: str

    @property
    def expires_soon(self) -> bool:
        """Return true when credentials should be refreshed."""
        return self.expiration <= datetime.now(UTC) + timedelta(minutes=5)


class SpiderVenomClient:
    """Small AWS Cognito + IoT Data client for Venom shadow reads."""

    def __init__(
        self,
        *,
        session: ClientSession,
        endpoint: str,
        identity_pool_id: str,
        region: str,
        thing_name: str,
    ) -> None:
        self._session = session
        self._endpoint = endpoint.removeprefix("https://").removeprefix("http://").strip("/")
        self._identity_pool_id = identity_pool_id
        self._region = region
        self._thing_name = thing_name
        self._credentials: _Credentials | None = None

    async def async_get_shadow(self) -> dict[str, Any]:
        """Fetch the current AWS IoT thing shadow."""
        return await self._async_iot_shadow_request(method="GET", payload="")

    async def async_set_target_temperature(self, temperature: int) -> dict[str, Any]:
        """Set the Venom target temperature."""
        return await self.async_update_desired({"heat": {"t2": {"trgt": temperature}}})

    async def async_update_desired(self, desired: dict[str, Any]) -> dict[str, Any]:
        """Update desired shadow state."""
        payload = json.dumps({"state": {"desired": desired}}, separators=(",", ":"))
        return await self._async_iot_shadow_request(method="POST", payload=payload)

    async def async_test_connection(self) -> dict[str, Any]:
        """Fetch a shadow once to validate config."""
        return await self.async_get_shadow()

    async def _async_iot_shadow_request(self, *, method: str, payload: str) -> dict[str, Any]:
        """Call the AWS IoT thing shadow endpoint."""
        credentials = await self._async_get_credentials()
        path = f"/things/{quote(self._thing_name, safe='')}/shadow"
        url = f"https://{self._endpoint}{path}"
        headers = self._signed_headers(
            method=method,
            path=path,
            query_string="",
            payload=payload,
            credentials=credentials,
            service="iotdata",
        )
        if payload:
            headers["Content-Type"] = "application/json"

        try:
            async with self._session.request(
                method, url, headers=headers, data=payload or None
            ) as response:
                body = await response.text()
                _log_response_body(f"IoT shadow {method}", response.status, body)
        except ClientConnectorError as err:
            raise SpiderVenomApiError(
                f"IoT shadow request could not connect to {self._endpoint}: {err}"
            ) from err
        except (TimeoutError, socket.gaierror) as err:
            raise SpiderVenomApiError(
                f"IoT shadow request timed out or DNS failed for {self._endpoint}: {err}"
            ) from err
        except ClientError as err:
            raise SpiderVenomApiError(f"IoT shadow request failed: {err}") from err

        if response.status != 200:
            raise SpiderVenomApiError(
                f"IoT shadow request returned HTTP {response.status}: {body[:300]}"
            )

        try:
            parsed = json.loads(body)
        except json.JSONDecodeError as err:
            raise SpiderVenomApiError("IoT shadow response was not JSON") from err

        if not isinstance(parsed, dict):
            raise SpiderVenomApiError("IoT shadow response had an unexpected shape")
        return parsed

    async def _async_get_credentials(self) -> _Credentials:
        if self._credentials is not None and not self._credentials.expires_soon:
            return self._credentials

        identity_id = await self._async_cognito_post(
            "GetId", {"IdentityPoolId": self._identity_pool_id}
        )
        identity = identity_id.get("IdentityId")
        if not isinstance(identity, str):
            raise SpiderVenomApiError("Cognito GetId response did not include IdentityId")

        credential_response = await self._async_cognito_post(
            "GetCredentialsForIdentity", {"IdentityId": identity}
        )
        credentials = credential_response.get("Credentials")
        if not isinstance(credentials, dict):
            raise SpiderVenomApiError(
                "Cognito GetCredentialsForIdentity response did not include credentials"
            )

        try:
            expiration = datetime.fromtimestamp(float(credentials["Expiration"]), UTC)
            self._credentials = _Credentials(
                access_key_id=credentials["AccessKeyId"],
                secret_key=credentials["SecretKey"],
                session_token=credentials["SessionToken"],
                expiration=expiration,
                identity_id=identity,
            )
        except (KeyError, TypeError, ValueError) as err:
            raise SpiderVenomApiError("Cognito credentials response was incomplete") from err

        return self._credentials

    async def _async_cognito_post(self, target: str, payload: dict[str, Any]) -> dict[str, Any]:
        url = f"https://cognito-identity.{self._region}.amazonaws.com/"
        headers = {
            "Content-Type": "application/x-amz-json-1.1",
            "X-Amz-Target": f"AWSCognitoIdentityService.{target}",
        }

        try:
            async with self._session.post(url, headers=headers, json=payload) as response:
                body = await response.text()
                _log_response_body(f"Cognito {target}", response.status, body)
        except ClientConnectorError as err:
            raise SpiderVenomApiError(
                f"Cognito {target} could not connect in region {self._region}: {err}"
            ) from err
        except (TimeoutError, socket.gaierror) as err:
            raise SpiderVenomApiError(
                f"Cognito {target} timed out or DNS failed in region {self._region}: {err}"
            ) from err
        except ClientError as err:
            raise SpiderVenomApiError(f"Cognito {target} request failed: {err}") from err

        try:
            parsed = json.loads(body)
        except json.JSONDecodeError as err:
            raise SpiderVenomApiError(f"Cognito {target} response was not JSON") from err

        if response.status != 200:
            error_type = parsed.get("__type", "unknown") if isinstance(parsed, dict) else "unknown"
            raise SpiderVenomApiError(
                f"Cognito {target} returned HTTP {response.status}: {error_type}"
            )

        if not isinstance(parsed, dict):
            raise SpiderVenomApiError(f"Cognito {target} response had an unexpected shape")
        return parsed

    def _signed_headers(
        self,
        *,
        method: str,
        path: str,
        query_string: str,
        payload: str,
        credentials: _Credentials,
        service: str,
    ) -> dict[str, str]:
        now = datetime.now(UTC)
        amz_date = now.strftime("%Y%m%dT%H%M%SZ")
        date_stamp = now.strftime("%Y%m%d")
        payload_hash = hashlib.sha256(payload.encode()).hexdigest()

        headers = {
            "host": self._endpoint,
            "x-amz-date": amz_date,
            "x-amz-security-token": credentials.session_token,
        }
        signed_headers = ";".join(sorted(headers))
        canonical_headers = "".join(f"{key}:{headers[key]}\n" for key in sorted(headers))
        canonical_request = "\n".join(
            [method, path, query_string, canonical_headers, signed_headers, payload_hash]
        )

        credential_scope = f"{date_stamp}/{self._region}/{service}/aws4_request"
        string_to_sign = "\n".join(
            [
                "AWS4-HMAC-SHA256",
                amz_date,
                credential_scope,
                hashlib.sha256(canonical_request.encode()).hexdigest(),
            ]
        )
        signature = hmac.new(
            self._signing_key(credentials.secret_key, date_stamp, service),
            string_to_sign.encode(),
            hashlib.sha256,
        ).hexdigest()

        return {
            "Authorization": (
                "AWS4-HMAC-SHA256 "
                f"Credential={credentials.access_key_id}/{credential_scope}, "
                f"SignedHeaders={signed_headers}, Signature={signature}"
            ),
            "x-amz-date": amz_date,
            "x-amz-security-token": credentials.session_token,
        }

    def _signing_key(self, secret_key: str, date_stamp: str, service: str) -> bytes:
        key_date = hmac.new(("AWS4" + secret_key).encode(), date_stamp.encode(), hashlib.sha256).digest()
        key_region = hmac.new(key_date, self._region.encode(), hashlib.sha256).digest()
        key_service = hmac.new(key_region, service.encode(), hashlib.sha256).digest()
        return hmac.new(key_service, b"aws4_request", hashlib.sha256).digest()


class SpiderGrillsAccountClient:
    """Client for Spider Grills account/device discovery."""

    def __init__(self, *, session: ClientSession, base_url: str = "https://spidergrills.app") -> None:
        self._session = session
        self._base_url = base_url.rstrip("/")

    async def async_login(self, *, email: str, password: str) -> str:
        """Log in and return an access token."""
        response = await self._async_request(
            "POST",
            "/auth/login",
            json_payload={"email": email, "password": password},
        )
        token = response.get("accessToken")
        if not isinstance(token, str) or not token:
            raise SpiderVenomApiError("Login response did not include an access token")
        return token

    async def async_get_devices(self, access_token: str) -> list[dict[str, Any]]:
        """Fetch devices for the logged-in account."""
        response = await self._async_request("GET", "/api/devices", access_token=access_token)
        if isinstance(response, list):
            devices = response
        elif isinstance(response.get("data"), list):
            devices = response["data"]
        elif isinstance(response.get("devices"), list):
            devices = response["devices"]
        else:
            raise SpiderVenomApiError("Devices response had an unexpected shape")

        return [device for device in devices if isinstance(device, dict)]

    async def _async_request(
        self,
        method: str,
        path: str,
        *,
        json_payload: dict[str, Any] | None = None,
        access_token: str | None = None,
    ) -> Any:
        headers = {"Accept": "application/json"}
        if json_payload is not None:
            headers["Content-Type"] = "application/json"
        if access_token:
            headers["Authorization"] = f"Bearer {access_token}"

        try:
            async with self._session.request(
                method,
                f"{self._base_url}{path}",
                headers=headers,
                json=json_payload,
            ) as response:
                body = await response.text()
                _log_response_body(f"Spider Grills API {method} {path}", response.status, body)
        except ClientConnectorError as err:
            raise SpiderVenomApiError(f"Spider Grills API could not connect: {err}") from err
        except (TimeoutError, socket.gaierror) as err:
            raise SpiderVenomApiError(f"Spider Grills API timed out or DNS failed: {err}") from err
        except ClientError as err:
            raise SpiderVenomApiError(f"Spider Grills API request failed: {err}") from err

        try:
            parsed = json.loads(body) if body else {}
        except json.JSONDecodeError as err:
            raise SpiderVenomApiError("Spider Grills API response was not JSON") from err

        if response.status < 200 or response.status >= 300:
            raise SpiderVenomApiError(f"Spider Grills API returned HTTP {response.status}")

        return parsed


def _log_response_body(label: str, status: int, body: str) -> None:
    """Log response bodies for local API discovery without leaking auth secrets."""
    if not _LOGGER.isEnabledFor(logging.DEBUG):
        return

    _LOGGER.debug("%s returned HTTP %s body: %s", label, status, _redacted_body(body))


def _redacted_body(body: str) -> str:
    if not body:
        return ""

    try:
        parsed = json.loads(body)
    except json.JSONDecodeError:
        return body

    return json.dumps(_redact_value(parsed), sort_keys=True)


def _redact_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: "***REDACTED***" if _is_sensitive_key(key) else _redact_value(child)
            for key, child in value.items()
        }
    if isinstance(value, list):
        return [_redact_value(child) for child in value]
    return value


def _is_sensitive_key(key: str) -> bool:
    normalized = key.lower()
    return normalized in _REDACTED_KEYS or normalized.endswith("token")
