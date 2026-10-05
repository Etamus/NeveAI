from http.cookies import SimpleCookie

from starlette.datastructures import MutableHeaders
from starlette.middleware.sessions import SessionMiddleware
from starlette.requests import HTTPConnection

from neveai.internal.legacy_state import LEGACY_SESSION_COOKIE


class NeveSessionMiddleware(SessionMiddleware):
    """Issue NeveAI cookies while accepting sessions created before the rename."""

    async def __call__(self, scope, receive, send):
        imported_cookie = None
        if scope["type"] in {"http", "websocket"}:
            cookies = HTTPConnection(scope).cookies
            if self.session_cookie not in cookies and LEGACY_SESSION_COOKIE in cookies:
                scope = dict(scope)
                headers = list(scope.get("headers", []))
                # Append to the existing cookie header so unrelated cookies are preserved.
                headers = [
                    (key, value) for key, value in headers if key.lower() != b"cookie"
                ]
                cookies[self.session_cookie] = cookies[LEGACY_SESSION_COOKIE]
                imported_cookie = cookies[self.session_cookie]

                cookie_header = SimpleCookie()
                for key, value in cookies.items():
                    cookie_header[key] = value
                headers.append(
                    (
                        b"cookie",
                        cookie_header.output(header="", sep=";")
                        .strip()
                        .encode("latin-1"),
                    )
                )
                scope["headers"] = headers

        async def send_response(message):
            if (
                imported_cookie
                and message["type"] == "http.response.start"
                and scope.get("session")
            ):
                headers = MutableHeaders(scope=message)
                if not any(
                    value.startswith(f"{self.session_cookie}=")
                    for value in headers.getlist("set-cookie")
                ):
                    expiry = f"Max-Age={self.max_age}; " if self.max_age else ""
                    headers.append(
                        "set-cookie",
                        f"{self.session_cookie}={imported_cookie}; "
                        f"path={self.path}; {expiry}{self.security_flags}",
                    )
            await send(message)

        await super().__call__(scope, receive, send_response)
