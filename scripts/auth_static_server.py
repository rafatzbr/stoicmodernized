#!/usr/bin/env python3
"""Small Basic Auth static server for the Stoic Modernized media explorer.

The public media origin intentionally serves generated review/upload artifacts.
Run this behind the existing media.zweb.ca tunnel to require one shared username
and password before any explorer page, video, or file is returned.
"""

from __future__ import annotations

import argparse
import base64
import hmac
import os
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path


REALM = os.environ.get("STOIC_MEDIA_AUTH_REALM", "Stoic Modernized Media")


class AuthenticatedStaticHandler(SimpleHTTPRequestHandler):
    """SimpleHTTPRequestHandler with HTTP Basic Auth on every request."""

    server_version = "StoicMediaAuthHTTP/1.0"

    def _expected_credentials(self) -> tuple[str, str]:
        username = os.environ.get("STOIC_MEDIA_USERNAME", "")
        password = os.environ.get("STOIC_MEDIA_PASSWORD", "")
        if not username or not password:
            raise RuntimeError(
                "STOIC_MEDIA_USERNAME and STOIC_MEDIA_PASSWORD must be set"
            )
        return username, password

    def _authorized(self) -> bool:
        header = self.headers.get("Authorization", "")
        if not header.startswith("Basic "):
            return False
        try:
            decoded = base64.b64decode(header[6:].strip(), validate=True).decode(
                "utf-8"
            )
        except Exception:
            return False
        username, sep, password = decoded.partition(":")
        if sep != ":":
            return False
        expected_username, expected_password = self._expected_credentials()
        return hmac.compare_digest(username, expected_username) and hmac.compare_digest(
            password, expected_password
        )

    def _send_auth_required(self) -> None:
        self.send_response(401)
        self.send_header("WWW-Authenticate", f'Basic realm="{REALM}", charset="UTF-8"')
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(b"Authentication required.\n")

    def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
        if not self._authorized():
            self._send_auth_required()
            return
        super().do_GET()

    def do_HEAD(self) -> None:  # noqa: N802 - stdlib handler API
        if not self._authorized():
            self._send_auth_required()
            return
        super().do_HEAD()


class ReuseAddressThreadingHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = True


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bind", default="0.0.0.0", help="Bind address")
    parser.add_argument("--port", type=int, default=8765, help="Listen port")
    parser.add_argument(
        "--directory",
        default="/home/rafatz/projects/stoic-modernized/output/social_public",
        help="Directory to serve",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    directory = Path(args.directory).expanduser().resolve()
    if not directory.is_dir():
        raise SystemExit(f"Directory does not exist: {directory}")
    if not os.environ.get("STOIC_MEDIA_USERNAME") or not os.environ.get(
        "STOIC_MEDIA_PASSWORD"
    ):
        raise SystemExit("Set STOIC_MEDIA_USERNAME and STOIC_MEDIA_PASSWORD")

    handler = lambda *h_args, **h_kwargs: AuthenticatedStaticHandler(  # noqa: E731
        *h_args, directory=str(directory), **h_kwargs
    )
    server = ReuseAddressThreadingHTTPServer((args.bind, args.port), handler)
    print(
        f"Serving {directory} on http://{args.bind}:{args.port}/ with Basic Auth",
        flush=True,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
