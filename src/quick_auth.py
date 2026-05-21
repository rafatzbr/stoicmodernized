#!/usr/bin/env python3
"""Quick OAuth2 token exchange using a pre-existing auth code + code_verifier."""
import sys
import hashlib
import base64
import json
import requests
from pathlib import Path

def main():
    if len(sys.argv) < 2 or len(sys.argv) > 4:
        print("Usage: python -m src.quick_auth <auth_code> <code_verifier> [channel_dir]")
        print("\nOr generate a new URL first:")
        print("  python -m src.quick_auth --genurl")
        print("\nThen authenticate and pass the code:")
        print("  python -m src.quick_auth <code> <code_verifier> [channel_dir]")
        sys.exit(1)

    if sys.argv[1] == "--genurl":
        import secrets
        verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode().rstrip('=')
        challenge = base64.urlsafe_b64encode(
            hashlib.sha256(verifier.encode()).digest()
        ).decode().rstrip('=')
        import urllib.parse
        params = {
            'response_type': 'code',
            'client_id': '889658691522-cgu6k0kk97uajv4nq3k78n1uf3o4jbl8.apps.googleusercontent.com',
            'redirect_uri': 'http://localhost',
            'scope': 'https://www.googleapis.com/auth/youtube.upload https://www.googleapis.com/auth/youtube.readonly',
            'state': secrets.token_urlsafe(24),
            'code_challenge': challenge,
            'code_challenge_method': 'S256',
            'access_type': 'offline',
            'include_granted_scopes': 'true',
            'prompt': 'consent',
        }
        url = 'https://accounts.google.com/o/oauth2/auth?' + urllib.parse.urlencode(params)
        print("OPEN THIS URL:")
        print(url)
        print("\nSAVE THIS CODE_VERIFIER (needed to exchange the code):")
        print(verifier)
        return

    auth_code = sys.argv[1]
    code_verifier = sys.argv[2] if len(sys.argv) > 2 else None

    if not code_verifier:
        print("Error: code_verifier required. Pass it as second argument.")
        print("Generate one with: python -m src.quick_auth --genurl")
        sys.exit(1)

    # Load client secret
    creds_file = Path.home() / ".stoic-modernized" / "client_secret.json"
    with open(creds_file) as f:
        client_data = json.load(f)

    # Exchange code for token
    token_url = "https://oauth2.googleapis.com/token"
    data = {
        "client_id": client_data["installed"]["client_id"],
        "client_secret": client_data["installed"]["client_secret"],
        "code": auth_code,
        "grant_type": "authorization_code",
        "redirect_uri": "http://localhost",
        "code_verifier": code_verifier,
    }

    resp = requests.post(token_url, data=data)
    result = resp.json()

    if "error" in result:
        print(f"Error: {result['error']} - {result.get('error_description', '')}")
        sys.exit(1)

    # Save token to channel-specific path
    channel_dir = sys.argv[3] if len(sys.argv) > 3 else "stoic-modernized"
    token_file = Path.home() / ".stoic-modernized" / channel_dir / "oauth2_token.json"
    token_file.parent.mkdir(parents=True, exist_ok=True)
    token_data = {
        "token": result["access_token"],
        "refresh_token": result.get("refresh_token"),
        "token_uri": token_url,
        "client_id": data["client_id"],
        "client_secret": data["client_secret"],
        "scopes": ["https://www.googleapis.com/auth/youtube.upload",
                    "https://www.googleapis.com/auth/youtube.readonly"],
        "expiry": result.get("expires_in"),
    }
    with open(token_file, "w") as f:
        json.dump(token_data, f, indent=2)

    print(f"\n✓ Token saved to: {token_file}")
    print("✓ OAuth2 authentication complete!")

if __name__ == "__main__":
    main()
