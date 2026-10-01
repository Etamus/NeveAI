import base64
import hashlib
import logging
import sys
import urllib
import json
from datetime import datetime, timedelta

import re
from cryptography.fernet import Fernet
from typing import Literal

import aiohttp
from authlib.integrations.starlette_client import OAuth
from fastapi import HTTPException
from starlette.responses import RedirectResponse
from typing import Optional


from neveai.models.oauth_sessions import OAuthSessions
from neveai.env import (
    AIOHTTP_CLIENT_SESSION_SSL,
    OAUTH_CLIENT_INFO_ENCRYPTION_KEY,
)

from mcp.shared.auth import (
    OAuthClientMetadata as MCPOAuthClientMetadata,
    OAuthMetadata,
)

from authlib.oauth2.rfc6749.errors import OAuth2Error


class OAuthClientMetadata(MCPOAuthClientMetadata):
    token_endpoint_auth_method: Literal[
        "none", "client_secret_basic", "client_secret_post"
    ] = "client_secret_post"
    pass


class OAuthClientInformationFull(OAuthClientMetadata):
    issuer: Optional[str] = None  # URL of the OAuth server that issued this client

    client_id: str
    client_secret: str | None = None
    client_id_issued_at: int | None = None
    client_secret_expires_at: int | None = None

    server_metadata: Optional[OAuthMetadata] = None  # Fetched from the OAuth server


from neveai.env import GLOBAL_LOG_LEVEL

logging.basicConfig(stream=sys.stdout, level=GLOBAL_LOG_LEVEL)
log = logging.getLogger(__name__)

FERNET = None

if len(OAUTH_CLIENT_INFO_ENCRYPTION_KEY) != 44:
    key_bytes = hashlib.sha256(OAUTH_CLIENT_INFO_ENCRYPTION_KEY.encode()).digest()
    OAUTH_CLIENT_INFO_ENCRYPTION_KEY = base64.urlsafe_b64encode(key_bytes)
else:
    OAUTH_CLIENT_INFO_ENCRYPTION_KEY = OAUTH_CLIENT_INFO_ENCRYPTION_KEY.encode()

try:
    FERNET = Fernet(OAUTH_CLIENT_INFO_ENCRYPTION_KEY)
except Exception as e:
    log.error(f"Error initializing Fernet with provided key: {e}")
    raise


def encrypt_data(data) -> str:
    """Encrypt data for storage"""
    try:
        data_json = json.dumps(data)
        encrypted = FERNET.encrypt(data_json.encode()).decode()
        return encrypted
    except Exception as e:
        log.error(f"Error encrypting data: {e}")
        raise


def decrypt_data(data: str):
    """Decrypt data from storage"""
    try:
        decrypted = FERNET.decrypt(data.encode()).decode()
        return json.loads(decrypted)
    except Exception as e:
        log.error(f"Error decrypting data: {e}")
        raise


def _build_oauth_callback_error_message(e: Exception) -> str:
    """
    Produce a user-facing callback error string with actionable context.
    Keeps the message short and strips newlines for safe redirect usage.
    """
    if isinstance(e, OAuth2Error):
        parts = [p for p in [e.error, e.description] if p]
        detail = " - ".join(parts)
    elif isinstance(e, HTTPException):
        detail = e.detail if isinstance(e.detail, str) else str(e.detail)
    elif isinstance(e, aiohttp.ClientResponseError):
        detail = f"Upstream provider returned {e.status}: {e.message}"
    elif isinstance(e, aiohttp.ClientError):
        detail = str(e)
    elif isinstance(e, KeyError):
        missing = str(e).strip("'")
        if missing.lower() == "state":
            detail = "Missing state parameter in callback (session may have expired)"
        else:
            detail = f"Missing expected key '{missing}' in OAuth response"
    else:
        detail = str(e)

    detail = detail.replace("\n", " ").strip()
    if not detail:
        detail = e.__class__.__name__

    message = f"OAuth callback failed: {detail}"
    return message[:197] + "..." if len(message) > 200 else message


def get_parsed_and_base_url(server_url) -> tuple[urllib.parse.ParseResult, str]:
    parsed = urllib.parse.urlparse(server_url)
    base_url = f"{parsed.scheme}://{parsed.netloc}"
    return parsed, base_url


async def get_authorization_server_discovery_urls(server_url: str) -> list[str]:
    """
    https://modelcontextprotocol.io/specification/2025-03-26/basic/authorization
    """

    authorization_servers = []
    try:
        async with aiohttp.ClientSession(trust_env=True) as session:
            async with session.post(
                server_url,
                json={"jsonrpc": "2.0", "method": "initialize", "params": {}, "id": 1},
                headers={"Content-Type": "application/json"},
                ssl=AIOHTTP_CLIENT_SESSION_SSL,
            ) as response:
                if response.status == 401:
                    match = re.search(
                        r'resource_metadata="([^"]+)"',
                        response.headers.get("WWW-Authenticate", ""),
                    )
                    if match:
                        resource_metadata_url = match.group(1)
                        log.debug(
                            f"Found resource_metadata URL: {resource_metadata_url}"
                        )

                        # Step 2: Fetch Protected Resource metadata
                        async with session.get(
                            resource_metadata_url, ssl=AIOHTTP_CLIENT_SESSION_SSL
                        ) as resource_response:
                            if resource_response.status == 200:
                                resource_metadata = await resource_response.json()

                                # Step 3: Extract authorization_servers
                                servers = resource_metadata.get(
                                    "authorization_servers", []
                                )
                                if servers:
                                    authorization_servers = servers
                                    log.debug(
                                        f"Discovered authorization servers: {servers}"
                                    )
    except Exception as e:
        log.debug(f"MCP Protected Resource discovery failed: {e}")

    discovery_urls = []
    for auth_server in authorization_servers:
        auth_server = auth_server.rstrip("/")
        discovery_urls.extend(
            [
                f"{auth_server}/.well-known/oauth-authorization-server",
                f"{auth_server}/.well-known/openid-configuration",
            ]
        )

    return discovery_urls


async def get_discovery_urls(server_url) -> list[str]:
    urls = await get_authorization_server_discovery_urls(server_url)
    parsed, base_url = get_parsed_and_base_url(server_url)

    if parsed.path and parsed.path != "/":
        # Generate discovery URLs based on https://modelcontextprotocol.io/specification/draft/basic/authorization#authorization-server-metadata-discovery
        tenant = parsed.path.rstrip("/")
        urls.extend(
            [
                urllib.parse.urljoin(
                    base_url,
                    f"/.well-known/oauth-authorization-server{tenant}",
                ),
                urllib.parse.urljoin(
                    base_url, f"/.well-known/openid-configuration{tenant}"
                ),
                urllib.parse.urljoin(
                    base_url, f"{tenant}/.well-known/openid-configuration"
                ),
            ]
        )

    urls.extend(
        [
            urllib.parse.urljoin(base_url, "/.well-known/oauth-authorization-server"),
            urllib.parse.urljoin(base_url, "/.well-known/openid-configuration"),
        ]
    )

    return urls


# TODO: Some OAuth providers require Initial Access Tokens (IATs) for dynamic client registration.
# This is not currently supported.
async def get_oauth_client_info_with_dynamic_client_registration(
    request,
    client_id: str,
    oauth_server_url: str,
    oauth_server_key: Optional[str] = None,
) -> OAuthClientInformationFull:
    try:
        oauth_server_metadata = None
        oauth_server_metadata_url = None

        redirect_base_url = (
            str(request.app.state.config.NEVEAI_URL or request.base_url)
        ).rstrip("/")

        oauth_client_metadata = OAuthClientMetadata(
            client_name="Neve",
            redirect_uris=[f"{redirect_base_url}/oauth/clients/{client_id}/callback"],
            grant_types=["authorization_code", "refresh_token"],
            response_types=["code"],
        )

        # Attempt to fetch OAuth server metadata to get registration endpoint & scopes
        discovery_urls = await get_discovery_urls(oauth_server_url)
        for url in discovery_urls:
            async with aiohttp.ClientSession(trust_env=True) as session:
                async with session.get(
                    url, ssl=AIOHTTP_CLIENT_SESSION_SSL
                ) as oauth_server_metadata_response:
                    if oauth_server_metadata_response.status == 200:
                        try:
                            oauth_server_metadata = OAuthMetadata.model_validate(
                                await oauth_server_metadata_response.json()
                            )
                            oauth_server_metadata_url = url
                            if (
                                oauth_client_metadata.scope is None
                                and oauth_server_metadata.scopes_supported is not None
                            ):
                                oauth_client_metadata.scope = " ".join(
                                    oauth_server_metadata.scopes_supported
                                )

                            if (
                                oauth_server_metadata.token_endpoint_auth_methods_supported
                                and oauth_client_metadata.token_endpoint_auth_method
                                not in oauth_server_metadata.token_endpoint_auth_methods_supported
                            ):
                                # Pick the first supported method from the server
                                oauth_client_metadata.token_endpoint_auth_method = oauth_server_metadata.token_endpoint_auth_methods_supported[
                                    0
                                ]

                            break
                        except Exception as e:
                            log.error(f"Error parsing OAuth metadata from {url}: {e}")
                            continue

        registration_url = None
        if oauth_server_metadata and oauth_server_metadata.registration_endpoint:
            registration_url = str(oauth_server_metadata.registration_endpoint)
        else:
            _, base_url = get_parsed_and_base_url(oauth_server_url)
            registration_url = urllib.parse.urljoin(base_url, "/register")

        registration_data = oauth_client_metadata.model_dump(
            exclude_none=True,
            mode="json",
            by_alias=True,
        )

        # Perform dynamic client registration and return client info
        async with aiohttp.ClientSession(trust_env=True) as session:
            async with session.post(
                registration_url, json=registration_data, ssl=AIOHTTP_CLIENT_SESSION_SSL
            ) as oauth_client_registration_response:
                try:
                    registration_response_json = (
                        await oauth_client_registration_response.json()
                    )

                    # The mcp package requires optional unset values to be None. If an empty string is passed, it gets validated and fails.
                    # This replaces all empty strings with None.
                    registration_response_json = {
                        k: (None if v == "" else v)
                        for k, v in registration_response_json.items()
                    }
                    oauth_client_info = OAuthClientInformationFull.model_validate(
                        {
                            **registration_response_json,
                            **{"issuer": oauth_server_metadata_url},
                            **{"server_metadata": oauth_server_metadata},
                        }
                    )
                    log.info(
                        f"Dynamic client registration successful at {registration_url}, client_id: {oauth_client_info.client_id}"
                    )
                    return oauth_client_info
                except Exception as e:
                    error_text = None
                    try:
                        error_text = await oauth_client_registration_response.text()
                        log.error(
                            f"Dynamic client registration failed at {registration_url}: {oauth_client_registration_response.status} - {error_text}"
                        )
                    except Exception as e:
                        pass

                    log.error(f"Error parsing client registration response: {e}")
                    raise Exception(
                        f"Dynamic client registration failed: {error_text}"
                        if error_text
                        else "Error parsing client registration response"
                    )
        raise Exception("Dynamic client registration failed")
    except Exception as e:
        log.error(f"Exception during dynamic client registration: {e}")
        raise e


class OAuthClientManager:
    def __init__(self, app):
        self.oauth = OAuth()
        self.app = app
        self.clients = {}

    def add_client(self, client_id, oauth_client_info: OAuthClientInformationFull):
        kwargs = {
            "name": client_id,
            "client_id": oauth_client_info.client_id,
            "client_secret": oauth_client_info.client_secret,
            "client_kwargs": {
                **(
                    {"scope": oauth_client_info.scope}
                    if oauth_client_info.scope
                    else {}
                ),
                **(
                    {
                        "token_endpoint_auth_method": oauth_client_info.token_endpoint_auth_method
                    }
                    if oauth_client_info.token_endpoint_auth_method
                    else {}
                ),
            },
            "server_metadata_url": (
                oauth_client_info.issuer if oauth_client_info.issuer else None
            ),
        }

        if (
            oauth_client_info.server_metadata
            and oauth_client_info.server_metadata.code_challenge_methods_supported
        ):
            if (
                isinstance(
                    oauth_client_info.server_metadata.code_challenge_methods_supported,
                    list,
                )
                and "S256"
                in oauth_client_info.server_metadata.code_challenge_methods_supported
            ):
                kwargs["code_challenge_method"] = "S256"

        self.clients[client_id] = {
            "client": self.oauth.register(**kwargs),
            "client_info": oauth_client_info,
        }
        return self.clients[client_id]

    def ensure_client_from_config(self, client_id):
        """
        Lazy-load an OAuth client from the current TOOL_SERVER_CONNECTIONS
        config if it hasn't been registered on this node yet.
        """
        if client_id in self.clients:
            return self.clients[client_id]["client"]

        try:
            connections = getattr(self.app.state.config, "TOOL_SERVER_CONNECTIONS", [])
        except Exception:
            connections = []

        for connection in connections or []:
            if connection.get("type", "openapi") != "mcp":
                continue
            if connection.get("auth_type", "none") != "oauth_2.1":
                continue

            server_id = connection.get("info", {}).get("id")
            if not server_id:
                continue

            expected_client_id = f"mcp:{server_id}"
            if client_id != expected_client_id:
                continue

            oauth_client_info = connection.get("info", {}).get("oauth_client_info", "")
            if not oauth_client_info:
                continue

            try:
                oauth_client_info = decrypt_data(oauth_client_info)
                return self.add_client(
                    expected_client_id, OAuthClientInformationFull(**oauth_client_info)
                )["client"]
            except Exception as e:
                log.error(
                    f"Failed to lazily add OAuth client {expected_client_id} from config: {e}"
                )
                continue

        return None

    def remove_client(self, client_id):
        if client_id in self.clients:
            del self.clients[client_id]
            log.info(f"Removed OAuth client {client_id}")

        if hasattr(self.oauth, "_clients"):
            if client_id in self.oauth._clients:
                self.oauth._clients.pop(client_id, None)

        if hasattr(self.oauth, "_registry"):
            if client_id in self.oauth._registry:
                self.oauth._registry.pop(client_id, None)

        return True

    async def _preflight_authorization_url(
        self, client, client_info: OAuthClientInformationFull
    ) -> bool:
        # TODO: Replace this logic with a more robust OAuth client registration validation
        # Only perform preflight checks for Starlette OAuth clients
        if not hasattr(client, "create_authorization_url"):
            return True

        redirect_uri = None
        if client_info.redirect_uris:
            redirect_uri = str(client_info.redirect_uris[0])

        try:
            auth_data = await client.create_authorization_url(redirect_uri=redirect_uri)
            authorization_url = auth_data.get("url")

            if not authorization_url:
                return True
        except Exception as e:
            log.debug(
                f"Skipping OAuth preflight for client {client_info.client_id}: {e}",
            )
            return True

        try:
            async with aiohttp.ClientSession(trust_env=True) as session:
                async with session.get(
                    authorization_url,
                    allow_redirects=False,
                    ssl=AIOHTTP_CLIENT_SESSION_SSL,
                ) as resp:
                    if resp.status < 400:
                        return True
                    response_text = await resp.text()

                    error = None
                    error_description = ""

                    content_type = resp.headers.get("content-type", "")
                    if "application/json" in content_type:
                        try:
                            payload = json.loads(response_text)
                            error = payload.get("error")
                            error_description = payload.get("error_description", "")
                        except Exception:
                            pass
                    else:
                        error_description = response_text

                    error_message = f"{error or ''} {error_description or ''}".lower()

                    if any(
                        keyword in error_message
                        for keyword in ("invalid_client", "invalid client", "client id")
                    ):
                        log.warning(
                            f"OAuth client preflight detected invalid registration for {client_info.client_id}: {error} {error_description}"
                        )

                        return False
        except Exception as e:
            log.debug(
                f"Skipping OAuth preflight network check for client {client_info.client_id}: {e}"
            )

        return True

    def get_client(self, client_id):
        if client_id not in self.clients:
            self.ensure_client_from_config(client_id)

        client = self.clients.get(client_id)
        return client["client"] if client else None

    def get_client_info(self, client_id):
        if client_id not in self.clients:
            self.ensure_client_from_config(client_id)

        client = self.clients.get(client_id)
        return client["client_info"] if client else None

    def get_server_metadata_url(self, client_id):
        client = self.get_client(client_id)
        if not client:
            return None

        return (
            client._server_metadata_url
            if hasattr(client, "_server_metadata_url")
            else None
        )

    async def get_oauth_token(
        self, user_id: str, client_id: str, force_refresh: bool = False
    ):
        """
        Get a valid OAuth token for the user, automatically refreshing if needed.

        Args:
            user_id: The user ID
            client_id: The OAuth client ID (provider)
            force_refresh: Force token refresh even if current token appears valid

        Returns:
            dict: OAuth token data with access_token, or None if no valid token available
        """
        try:
            # Get the OAuth session
            session = OAuthSessions.get_session_by_provider_and_user_id(
                client_id, user_id
            )
            if not session:
                log.warning(
                    f"No OAuth session found for user {user_id}, client_id {client_id}"
                )
                return None

            if force_refresh or datetime.now() + timedelta(
                minutes=5
            ) >= datetime.fromtimestamp(session.expires_at):
                log.debug(
                    f"Token refresh needed for user {user_id}, client_id {session.provider}"
                )
                refreshed_token = await self._refresh_token(session)
                if refreshed_token:
                    return refreshed_token
                else:
                    log.warning(
                        f"Token refresh failed for user {user_id}, client_id {session.provider}, deleting session {session.id}"
                    )
                    OAuthSessions.delete_session_by_id(session.id)
                    return None
            return session.token

        except Exception as e:
            log.error(f"Error getting OAuth token for user {user_id}: {e}")
            return None

    async def _refresh_token(self, session) -> dict:
        """
        Refresh an OAuth token if needed, with concurrency protection.

        Args:
            session: The OAuth session object

        Returns:
            dict: Refreshed token data, or None if refresh failed
        """
        try:
            # Perform the actual refresh
            refreshed_token = await self._perform_token_refresh(session)

            if refreshed_token:
                # Update the session with new token data
                session = OAuthSessions.update_session_by_id(
                    session.id, refreshed_token
                )
                log.info(f"Successfully refreshed token for session {session.id}")
                return session.token
            else:
                log.error(f"Failed to refresh token for session {session.id}")
                return None

        except Exception as e:
            log.error(f"Error refreshing token for session {session.id}: {e}")
            return None

    async def _perform_token_refresh(self, session) -> dict:
        """
        Perform the actual OAuth token refresh.

        Args:
            session: The OAuth session object

        Returns:
            dict: New token data, or None if refresh failed
        """
        client_id = session.provider
        token_data = session.token

        if not token_data.get("refresh_token"):
            log.warning(f"No refresh token available for session {session.id}")
            return None

        try:
            client = self.get_client(client_id)
            if not client:
                log.error(f"No OAuth client found for provider {client_id}")
                return None

            token_endpoint = None
            async with aiohttp.ClientSession(trust_env=True) as session_http:
                async with session_http.get(
                    self.get_server_metadata_url(client_id)
                ) as r:
                    if r.status == 200:
                        openid_data = await r.json()
                        token_endpoint = openid_data.get("token_endpoint")
                    else:
                        log.error(
                            f"Failed to fetch OpenID configuration for client_id {client_id}"
                        )
            if not token_endpoint:
                log.error(f"No token endpoint found for client_id {client_id}")
                return None

            # Prepare refresh request
            refresh_data = {
                "grant_type": "refresh_token",
                "refresh_token": token_data["refresh_token"],
                "client_id": client.client_id,
            }
            if hasattr(client, "client_secret") and client.client_secret:
                refresh_data["client_secret"] = client.client_secret

            # Add scope if available in client kwargs (some providers require it on refresh)
            if (
                hasattr(client, "client_kwargs")
                and client.client_kwargs.get("scope")
                and getattr(
                    self.app.state.config, "OAUTH_REFRESH_TOKEN_INCLUDE_SCOPE", False
                )
            ):
                refresh_data["scope"] = client.client_kwargs["scope"]

            # Make refresh request
            async with aiohttp.ClientSession(trust_env=True) as session_http:
                async with session_http.post(
                    token_endpoint,
                    data=refresh_data,
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                    ssl=AIOHTTP_CLIENT_SESSION_SSL,
                ) as r:
                    if r.status == 200:
                        new_token_data = await r.json()

                        # Merge with existing token data (preserve refresh_token if not provided)
                        if "refresh_token" not in new_token_data:
                            new_token_data["refresh_token"] = token_data[
                                "refresh_token"
                            ]

                        # Add timestamp for tracking
                        new_token_data["issued_at"] = datetime.now().timestamp()

                        # Calculate expires_at if we have expires_in
                        if (
                            "expires_in" in new_token_data
                            and "expires_at" not in new_token_data
                        ):
                            new_token_data["expires_at"] = int(
                                datetime.now().timestamp()
                                + new_token_data["expires_in"]
                            )

                        log.debug(f"Token refresh successful for client_id {client_id}")
                        return new_token_data
                    else:
                        error_text = await r.text()
                        log.error(
                            f"Token refresh failed for client_id {client_id}: {r.status} - {error_text}"
                        )
                        return None

        except Exception as e:
            log.error(f"Exception during token refresh for client_id {client_id}: {e}")
            return None

    async def handle_authorize(self, request, client_id: str) -> RedirectResponse:
        client = self.get_client(client_id) or self.ensure_client_from_config(client_id)
        if client is None:
            raise HTTPException(404)
        client_info = self.get_client_info(client_id)
        if client_info is None:
            # ensure_client_from_config registers client_info too
            client_info = self.get_client_info(client_id)
        if client_info is None:
            raise HTTPException(404)

        redirect_uri = (
            client_info.redirect_uris[0] if client_info.redirect_uris else None
        )
        redirect_uri_str = str(redirect_uri) if redirect_uri else None
        return await client.authorize_redirect(request, redirect_uri_str)

    async def handle_callback(self, request, client_id: str, user_id: str, response):
        client = self.get_client(client_id) or self.ensure_client_from_config(client_id)
        if client is None:
            raise HTTPException(404)

        error_message = None
        try:
            client_info = self.get_client_info(client_id)

            # Note: Do NOT pass client_id/client_secret explicitly here.
            # The Authlib client already has these configured during add_client().
            # Passing them again causes Authlib to concatenate them (e.g., "ID1,ID1"),
            # which results in 401 errors from the token endpoint. (Fix for #19823)
            token = await client.authorize_access_token(request)

            # Validate that we received a proper token response
            # If token exchange failed (e.g., 401), we may get an error response instead
            if token and not token.get("access_token"):
                error_desc = token.get(
                    "error_description", token.get("error", "Unknown error")
                )
                error_message = f"Token exchange failed: {error_desc}"
                log.error(f"Invalid token response for client_id {client_id}: {token}")
                token = None

            if token:
                try:
                    # Add timestamp for tracking
                    token["issued_at"] = datetime.now().timestamp()

                    # Calculate expires_at if we have expires_in
                    if "expires_in" in token and "expires_at" not in token:
                        token["expires_at"] = (
                            datetime.now().timestamp() + token["expires_in"]
                        )

                    # Clean up any existing sessions for this user/client_id first
                    sessions = OAuthSessions.get_sessions_by_user_id(user_id)
                    for session in sessions:
                        if session.provider == client_id:
                            OAuthSessions.delete_session_by_id(session.id)

                    session = OAuthSessions.create_session(
                        user_id=user_id,
                        provider=client_id,
                        token=token,
                    )
                    log.info(
                        f"Stored OAuth session server-side for user {user_id}, client_id {client_id}"
                    )
                except Exception as e:
                    error_message = "Failed to store OAuth session server-side"
                    log.error(f"Failed to store OAuth session server-side: {e}")
            else:
                if not error_message:
                    error_message = "Failed to obtain OAuth token"
                log.warning(error_message)
        except Exception as e:
            error_message = _build_oauth_callback_error_message(e)
            log.warning(
                "OAuth callback error for user_id=%s client_id=%s: %s",
                user_id,
                client_id,
                error_message,
                exc_info=True,
            )

        redirect_url = (
            str(request.app.state.config.NEVEAI_URL or request.base_url)
        ).rstrip("/")

        if error_message:
            log.debug(error_message)
            redirect_url = (
                f"{redirect_url}/?error={urllib.parse.quote_plus(error_message)}"
            )
            return RedirectResponse(url=redirect_url, headers=response.headers)

        response = RedirectResponse(url=redirect_url, headers=response.headers)
        return response
