"""Client for Spider Grills Venom AWS IoT shadows."""

from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import hashlib
import hmac
import json
import logging
import re
import socket
import ssl
import threading
from typing import Any
from urllib.parse import quote
import uuid

from aiohttp import ClientConnectorError, ClientError, ClientSession, ClientTimeout
import paho.mqtt.client as mqtt

_LOGGER = logging.getLogger(__name__)
DEFAULT_TIMEOUT = ClientTimeout(total=15)
_MQTT_TIMEOUT = 15
_MQTT_CONNECT_TIMEOUT = 10.0
_MAX_DEBUG_LOG_CHARS = 4096
_MAX_NON_JSON_LOG_CHARS = 500
_REDACTED_KEYS = {
    "accesskeyid",
    "accesstoken",
    "apikey",
    "authorization",
    "cookie",
    "email",
    "identityid",
    "idtoken",
    "jwt",
    "password",
    "refreshtoken",
    "secret",
    "secretaccesskey",
    "secretkey",
    "sessiontoken",
}


class SpiderVenomApiError(Exception):
    """Raised when the Spider Grills cloud API cannot be reached."""

    def __init__(self, message: str, *, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


class SpiderVenomAuthError(SpiderVenomApiError):
    """Raised when Spider Grills authentication fails."""


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
    """AWS Cognito + IoT MQTT-over-WebSocket client for Venom shadows."""

    def __init__(
        self,
        *,
        session: ClientSession,
        endpoint: str,
        identity_pool_id: str,
        region: str,
        thing_name: str,
        timeout: ClientTimeout = DEFAULT_TIMEOUT,
        ssl_context: ssl.SSLContext | None = None,
    ) -> None:
        self._session = session
        self._endpoint = endpoint.removeprefix("https://").removeprefix("http://").strip("/")
        self._identity_pool_id = identity_pool_id
        self._region = region
        self._thing_name = thing_name
        self._timeout = timeout
        self._ssl_context = ssl_context
        self._ssl_context_lock = threading.Lock()
        self._credentials: _Credentials | None = None
        self._identity_id: str | None = None
        self._credentials_lock = asyncio.Lock()

    async def async_get_shadow(self) -> dict[str, Any]:
        """Fetch the current AWS IoT thing shadow."""
        return await self._async_iot_shadow_request(action="get", payload={})

    async def async_set_target_temperature(self, temperature: int) -> dict[str, Any]:
        """Set the Venom target temperature."""
        return await self.async_update_desired({"heat": {"t2": {"trgt": temperature}}})

    async def async_update_desired(self, desired: dict[str, Any]) -> dict[str, Any]:
        """Update desired shadow state."""
        return await self._async_iot_shadow_request(
            action="update",
            payload={"state": {"desired": desired}},
        )

    async def async_test_connection(self) -> dict[str, Any]:
        """Fetch a shadow once to validate config."""
        return await self.async_get_shadow()

    def _get_ssl_context(self) -> ssl.SSLContext:
        """Return a cached SSL context, creating it lazily off the event loop."""
        if self._ssl_context is None:
            with self._ssl_context_lock:
                if self._ssl_context is None:
                    self._ssl_context = ssl.create_default_context()
        return self._ssl_context

    async def _async_iot_shadow_request(
        self, *, action: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        """Call the AWS IoT thing shadow over MQTT-over-WebSocket.

        Since 2026-09-30 the guest Cognito role receives HTTP 403 on the REST shadow
        API, while MQTT-over-WebSocket remains permitted (matching the mobile app).
        """
        loop = asyncio.get_running_loop()
        for attempt in range(2):
            credentials = await self._async_get_credentials()
            token = uuid.uuid4().hex
            message = json.dumps({**payload, "clientToken": token}, separators=(",", ":"))
            ws_path = self._presigned_ws_path(credentials)
            try:
                return await loop.run_in_executor(
                    None,
                    self._mqtt_shadow_call,
                    ws_path,
                    action,
                    message,
                    token,
                )
            except SpiderVenomApiError as err:
                if err.status in (401, 403) and attempt == 0:
                    self._credentials = None
                    continue
                raise

        raise SpiderVenomApiError(f"IoT shadow {action} failed after credential refresh")

    def _mqtt_shadow_call(
        self, ws_path: str, action: str, message: str, token: str
    ) -> dict[str, Any]:
        topic = f"$aws/things/{self._thing_name}/shadow/{action}"
        done = threading.Event()
        result: dict[str, Any] = {}

        def finish(key: str, value: Any) -> None:
            if not done.is_set():
                result[key] = value
                done.set()

        def on_connect(
            mqtt_client: mqtt.Client,
            userdata: Any,
            flags: Any,
            reason_code: Any,
            properties: Any = None,
        ) -> None:
            if reason_code.is_failure:
                reason_str = str(reason_code)
                err_status = (
                    403
                    if any(
                        marker in reason_str.lower()
                        for marker in ("not authorized", "bad user name or password")
                    )
                    else None
                )
                finish("error", (f"MQTT connect refused: {reason_str}", err_status))
                return
            mqtt_client.subscribe([(f"{topic}/accepted", 1), (f"{topic}/rejected", 1)])

        def on_subscribe(
            mqtt_client: mqtt.Client,
            userdata: Any,
            mid: Any,
            reason_codes: Any,
            properties: Any = None,
        ) -> None:
            if any(code.is_failure for code in reason_codes):
                finish("error", (f"MQTT subscribe refused: {[str(c) for c in reason_codes]}", None))
                return
            mqtt_client.publish(topic, message, qos=1)

        def on_message(
            mqtt_client: mqtt.Client,
            userdata: Any,
            msg: mqtt.MQTTMessage,
        ) -> None:
            raw = msg.payload.decode("utf-8", errors="replace")
            try:
                doc = json.loads(raw)
            except ValueError:
                return
            # accepted/rejected topics are shared with the vendor app; match our request.
            if not isinstance(doc, dict) or doc.get("clientToken") != token:
                return
            if msg.topic.endswith("/rejected"):
                code = doc.get("code")
                err_status = code if isinstance(code, int) else 400
                _log_response_body(f"IoT shadow {action}", err_status, raw)
                finish(
                    "error",
                    (f"Shadow {action} rejected: {code} {doc.get('message')}", err_status),
                )
            else:
                _log_response_body(f"IoT shadow {action}", 200, raw)
                finish("doc", doc)

        def on_disconnect(
            mqtt_client: mqtt.Client,
            userdata: Any,
            flags: Any,
            reason_code: Any,
            properties: Any = None,
        ) -> None:
            reason_str = str(reason_code)
            err_status = (
                403
                if any(
                    marker in reason_str.lower()
                    for marker in ("not authorized", "bad user name or password")
                )
                else None
            )
            finish("error", (f"MQTT disconnected: {reason_str}", err_status))

        # AWS IoT policy only permits a dashed-UUID client id; Cognito identity IDs or
        # undashed hex UUIDs are disconnected before CONNACK.
        client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id=str(uuid.uuid4()),
            transport="websockets",
        )
        client.connect_timeout = _MQTT_CONNECT_TIMEOUT
        client.ws_set_options(path=ws_path)
        client.tls_set_context(self._get_ssl_context())
        client.on_connect = on_connect
        client.on_subscribe = on_subscribe
        client.on_message = on_message
        client.on_disconnect = on_disconnect

        try:
            client.connect(self._endpoint, 443, keepalive=30)
        except (OSError, ssl.SSLError) as err:
            err_msg = str(err)
            err_lower = err_msg.lower()
            err_status = (
                403
                if any(
                    marker in err_lower
                    for marker in ("401", "403", "forbidden", "unauthorized")
                )
                else None
            )
            raise SpiderVenomApiError(
                f"IoT MQTT could not connect to {self._endpoint}: {err_msg}",
                status=err_status,
            ) from err

        client.loop_start()
        try:
            if not done.wait(_MQTT_TIMEOUT):
                raise SpiderVenomApiError(f"IoT shadow {action} timed out after {_MQTT_TIMEOUT}s")
        finally:
            with contextlib.suppress(Exception):
                client.disconnect()
            client.loop_stop()

        if "error" in result:
            err_msg, err_status = result["error"]
            raise SpiderVenomApiError(err_msg, status=err_status)
        return result["doc"]

    async def _async_get_credentials(self) -> _Credentials:
        if self._credentials is not None and not self._credentials.expires_soon:
            return self._credentials

        async with self._credentials_lock:
            if self._credentials is not None and not self._credentials.expires_soon:
                return self._credentials

            identity = self._identity_id
            if identity is None:
                identity_id = await self._async_cognito_post(
                    "GetId", {"IdentityPoolId": self._identity_pool_id}
                )
                identity = identity_id.get("IdentityId")
                if not isinstance(identity, str) or not identity:
                    raise SpiderVenomApiError("Cognito GetId response did not include IdentityId")
                self._identity_id = identity

            try:
                credential_response = await self._async_cognito_post(
                    "GetCredentialsForIdentity", {"IdentityId": identity}
                )
            except SpiderVenomApiError as err:
                if err.status in (400, 401, 403):
                    self._identity_id = None
                raise

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
            async with self._session.post(
                url,
                headers=headers,
                json=payload,
                timeout=self._timeout,
            ) as response:
                body = await response.text()
                status = response.status
                _log_response_body(f"Cognito {target}", status, body)
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

        if status != 200:
            error_detail: str = body[:300]
            try:
                err_parsed = json.loads(body) if body else {}
            except json.JSONDecodeError:
                err_parsed = None
            if isinstance(err_parsed, dict) and "__type" in err_parsed:
                error_detail = str(err_parsed["__type"])
            raise SpiderVenomApiError(
                f"Cognito {target} returned HTTP {status}: {error_detail}",
                status=status,
            )

        try:
            parsed = json.loads(body)
        except json.JSONDecodeError as err:
            raise SpiderVenomApiError(f"Cognito {target} response was not JSON") from err

        if not isinstance(parsed, dict):
            raise SpiderVenomApiError(f"Cognito {target} response had an unexpected shape")
        return parsed

    def _presigned_ws_path(self, credentials: _Credentials) -> str:
        now = datetime.now(UTC)
        amz_date = now.strftime("%Y%m%dT%H%M%SZ")
        date_stamp = now.strftime("%Y%m%d")
        service = "iotdevicegateway"
        credential_scope = f"{date_stamp}/{self._region}/{service}/aws4_request"
        query = {
            "X-Amz-Algorithm": "AWS4-HMAC-SHA256",
            "X-Amz-Credential": f"{credentials.access_key_id}/{credential_scope}",
            "X-Amz-Date": amz_date,
            "X-Amz-SignedHeaders": "host",
        }
        query_string = "&".join(
            f"{key}={quote(value, safe='')}" for key, value in sorted(query.items())
        )
        canonical_request = "\n".join(
            [
                "GET",
                "/mqtt",
                query_string,
                f"host:{self._endpoint}\n",
                "host",
                hashlib.sha256(b"").hexdigest(),
            ]
        )
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
        # AWS IoT expects the session token appended after signing, not signed.
        return (
            f"/mqtt?{query_string}&X-Amz-Signature={signature}"
            f"&X-Amz-Security-Token={quote(credentials.session_token, safe='')}"
        )

    def _signing_key(self, secret_key: str, date_stamp: str, service: str) -> bytes:
        key_date = hmac.new(("AWS4" + secret_key).encode(), date_stamp.encode(), hashlib.sha256).digest()
        key_region = hmac.new(key_date, self._region.encode(), hashlib.sha256).digest()
        key_service = hmac.new(key_region, service.encode(), hashlib.sha256).digest()
        return hmac.new(key_service, b"aws4_request", hashlib.sha256).digest()


class SpiderGrillsAccountClient:
    """Client for Spider Grills account/device discovery."""

    def __init__(
        self,
        *,
        session: ClientSession,
        base_url: str = "https://spidergrills.app",
        timeout: ClientTimeout = DEFAULT_TIMEOUT,
    ) -> None:
        self._session = session
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    async def async_login(self, *, email: str, password: str) -> str:
        """Log in and return an access token."""
        response = await self._async_request(
            "POST",
            "/auth/login",
            json_payload={"email": email, "password": password},
        )
        if not isinstance(response, dict):
            raise SpiderVenomApiError("Login response had an unexpected shape")
        token = response.get("accessToken")
        if not isinstance(token, str) or not token:
            raise SpiderVenomApiError("Login response did not include an access token")
        return token

    async def async_get_devices(self, access_token: str) -> list[dict[str, Any]]:
        """Fetch devices for the logged-in account."""
        response = await self._async_request("GET", "/api/devices", access_token=access_token)
        if isinstance(response, list):
            devices = response
        elif isinstance(response, dict) and isinstance(response.get("data"), list):
            devices = response["data"]
        elif isinstance(response, dict) and isinstance(response.get("devices"), list):
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
                timeout=self._timeout,
            ) as response:
                body = await response.text()
                status = response.status
                _log_response_body(
                    f"Spider Grills API {method} {path}",
                    status,
                    body,
                    redact_non_json=(path == "/auth/login"),
                )
        except ClientConnectorError as err:
            raise SpiderVenomApiError(f"Spider Grills API could not connect: {err}") from err
        except (TimeoutError, socket.gaierror) as err:
            raise SpiderVenomApiError(f"Spider Grills API timed out or DNS failed: {err}") from err
        except ClientError as err:
            raise SpiderVenomApiError(f"Spider Grills API request failed: {err}") from err

        if status in (401, 403):
            raise SpiderVenomAuthError(
                f"Spider Grills API returned HTTP {status}",
                status=status,
            )
        if status < 200 or status >= 300:
            raise SpiderVenomApiError(
                f"Spider Grills API returned HTTP {status}",
                status=status,
            )

        try:
            return json.loads(body) if body else {}
        except json.JSONDecodeError as err:
            raise SpiderVenomApiError("Spider Grills API response was not JSON") from err


def _log_response_body(
    label: str,
    status: int,
    body: str,
    *,
    redact_non_json: bool = False,
) -> None:
    """Log response bodies for local API discovery without leaking auth secrets."""
    if not _LOGGER.isEnabledFor(logging.DEBUG):
        return

    _LOGGER.debug(
        "%s returned HTTP %s body: %s",
        label,
        status,
        _redacted_body(body, redact_non_json=redact_non_json),
    )


def _redacted_body(body: str, *, redact_non_json: bool = False) -> str:
    if not body:
        return ""

    try:
        parsed = json.loads(body)
    except json.JSONDecodeError:
        if redact_non_json:
            return "<non-JSON response body omitted>"
        return _truncate(body, _MAX_NON_JSON_LOG_CHARS)

    return _truncate(json.dumps(_redact_value(parsed), sort_keys=True), _MAX_DEBUG_LOG_CHARS)


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return f"{text[:limit]}...<truncated>"


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
    normalized = re.sub(r"[^a-z0-9]", "", key.lower())
    return normalized in _REDACTED_KEYS or normalized.endswith("token")
