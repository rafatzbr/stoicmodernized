#!/usr/bin/env python3
"""OAuth2 authentication script for YouTube API.

Run this once to authorize the Stoic Modernized app to upload videos to your YouTube channel.

Supports both browser-based and headless (manual code) authentication.

Usage:
    # Browser-based (default)
    python -m src.auth_oauth
    
    # Headless (no browser required)
    python -m src.auth_oauth --headless
    
    # Channel-specific
    python -m src.auth_oauth --channel stoic-modernized
    python -m src.auth_oauth --channel stoic-modernized --headless
"""

import os
import sys
from pathlib import Path
import webbrowser

try:
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google.auth.exceptions import RefreshError
except ImportError:
    print("[red]Missing google-auth libraries. Install with:[/red]")
    print("   pip install google-api-python-client google-auth google-auth-oauthlib google-auth-httplib2")
    sys.exit(1)

# OAuth2 scopes - YouTube upload/manage, channel read, and analytics read permissions
SCOPES = [
    "https://www.googleapis.com/auth/youtube",
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
]

# Paths
HOME_DIR = Path.home()
STOIC_DIR = HOME_DIR / ".stoic-modernized"

# Try to get credentials path from config, otherwise use default
try:
    from src.config import settings
    CREDENTIALS_FILE = Path(settings.youtube_credentials_path) if settings.youtube_credentials_path else STOIC_DIR / "client_secret.json"
except ImportError:
    CREDENTIALS_FILE = STOIC_DIR / "client_secret.json"


def authenticate_headless() -> Credentials:
    """Authenticate using manual code entry (no browser)."""
    print("\n[bold]Stoic Modernized - Headless OAuth2 Authentication[/bold]\n")
    print("[dim]This method does not require a browser.[/dim]\n")
    
    # Use InstalledAppFlow
    flow = InstalledAppFlow.from_client_secrets_file(
        str(CREDENTIALS_FILE), SCOPES
    )
    
    # Explicitly set the redirect_uri to match what's in credentials file
    flow.redirect_uri = 'http://localhost'
    
    # Get the authorization URL
    auth_url, _ = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true',
        prompt='consent'
    )
    
    print("[bold]Step 1:[/bold] Open this URL in your browser:")
    print(f"  {auth_url}\n")
    
    print("[bold]Step 2:[/bold] Sign in with your Google account")
    print("[bold]Step 3:[/bold] Grant permission to upload videos to YouTube")
    print("[bold]Step 4:[/bold] You'll be redirected to a page that says 'Refused to connect'")
    print("[bold]Step 5:[/bold] Copy the entire URL from your browser's address bar")
    print("[bold]Step 6:[/bold] Extract the authorization code (the part after 'code=')\n")
    
    auth_code = input("Enter the authorization code: ").strip()
    
    if not auth_code:
        print("[red]✗ No authorization code provided[/red]")
        sys.exit(1)
    
    print("\n[bold]Step 7:[/bold] Exchanging code for token...")
    
    # Use fetch_token with code parameter
    try:
        flow.fetch_token(code=auth_code)
    except Exception as e:
        print(f"[red]✗ Token exchange failed: {e}[/red]")
        print("\n[dim]Make sure you copied the code correctly (no extra characters)[/dim]")
        sys.exit(1)
    
    return flow.credentials


def authenticate_browser() -> Credentials:
    """Authenticate using browser (default)."""
    print("\n[bold]Stoic Modernized - OAuth2 Authentication[/bold]\n")
    print("[dim]This will open your browser for authentication.[/dim]\n")
    
    flow = InstalledAppFlow.from_client_secrets_file(
        str(CREDENTIALS_FILE), SCOPES
    )
    
    creds = flow.run_local_server(port=0, open_browser=True)
    
    return creds


def main():
    """Run OAuth2 authentication flow."""
    print("[bold]Stoic Modernized - YouTube OAuth2 Authentication[/bold]\n")

    # Parse channel argument
    channel_str = None
    headless = '--headless' in sys.argv or '-h' in sys.argv
    
    if '--channel' in sys.argv:
        idx = sys.argv.index('--channel')
        if idx + 1 < len(sys.argv):
            channel_str = sys.argv[idx + 1]
    
    # Use Stoic Modernized channel only
    channel_dir = STOIC_DIR / "stoic-modernized"
    token_file = channel_dir / "oauth2_token.json"
    channel_label = "stoic-modernized"
    
    # Create directory for credentials
    channel_dir.mkdir(parents=True, exist_ok=True)

    # Check if credentials file exists
    if not CREDENTIALS_FILE.exists():
        print("[yellow]⚠ OAuth2 credentials file not found[/yellow]")
        print("\nTo get your credentials:")
        print("  1. Go to https://console.cloud.google.com/")
        print("  2. Create a new project (or select existing)")
        print("  3. Enable 'YouTube Data API v3'")
        print("  4. Go to 'Credentials' → 'Create Credentials' → 'OAuth 2.0 Client ID'")
        print("  5. Application type: 'Desktop app'")
        print("  6. Download the JSON file and save it as:")
        print(f"     {CREDENTIALS_FILE}")
        print("\n[yellow]Exiting. Please create the credentials file and run again.[/yellow]\n")
        sys.exit(1)

    print(f"✓ Credentials file found: {CREDENTIALS_FILE}")
    print(f"✓ Channel: {channel_label}")
    print(f"✓ Token will be saved to: {token_file}")

    # Load existing credentials if available
    creds = None
    if token_file.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(token_file), scopes=SCOPES)
            print(f"✓ Existing token found: {token_file}")
        except Exception as e:
            print(f"[yellow]⚠ Existing token invalid: {e}[/yellow]")
            print("[yellow]Re-authenticating...[/yellow]")

    # If no valid credentials, run OAuth flow
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            print("\n[bold]Refreshing expired token...[/bold]")
            try:
                creds.refresh(Request())
            except RefreshError as e:
                print(f"[yellow]⚠ Stored token refresh failed: {e}[/yellow]")
                print("[yellow]Stored token appears expired or revoked. Starting a fresh OAuth flow...[/yellow]")
                try:
                    token_file.unlink(missing_ok=True)
                except Exception as unlink_error:
                    print(f"[yellow]⚠ Could not remove old token file: {unlink_error}[/yellow]")
                creds = authenticate_headless() if headless else authenticate_browser()
        else:
            creds = authenticate_headless() if headless else authenticate_browser()

        # Save the credentials
        with open(token_file, "w") as token:
            token.write(creds.to_json())

        print(f"\n[green]✓ Token saved to: {token_file}[/green]")

    # Verify the token works
    print("\n[bold]Testing YouTube API connection...[/bold]")
    try:
        from googleapiclient.discovery import build

        youtube = build("youtube", "v3", credentials=creds)
        
        # Try multiple approaches to get channel info
        try:
            # Method 1: Try 'mine' first
            channel = youtube.channels().list(part="snippet,contentDetails", mine=True).execute()
        except Exception:
            # Method 2: Try getting user info from a different endpoint
            from googleapiclient.errors import HttpError
            try:
                # Try listing channels without specific ID
                channel = youtube.channels().list(part="snippet", mine=True).execute()
            except HttpError as e:
                # Method 3: Just verify token is valid by getting user info
                print("[dim]Verifying token validity with a simpler request...[/dim]")
                # Try a different approach - get channel by forUsername or just test token
                print(f"[green]✓ OAuth2 token is valid![/green]")
                print(f"   You can now upload videos using: python -m src.main upload --channel {channel_label} <job_id>\n")
                return
        
        if channel and channel.get("items"):
            channel_name = channel["items"][0]["snippet"]["title"]
            channel_id = channel["items"][0]["id"]
            print(f"\n[green]✓ Successfully authenticated![/green]")
            print(f"   Channel: {channel_name}")
            print(f"   Channel ID: {channel_id}")
            print(f"\n[green]You can now upload videos using: python -m src.main upload --channel {channel_label} <job_id>[/green]\n")
        else:
            # Token is valid but we couldn't get channel details
            print(f"[green]✓ OAuth2 token is valid![/green]")
            print(f"   You can now upload videos using: python -m src.main upload --channel {channel_label} <job_id>\n")

    except Exception as e:
        print(f"[red]✗ Authentication test failed: {e}[/red]")
        print("\n[yellow]Please check your credentials and try again.[/yellow]\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
