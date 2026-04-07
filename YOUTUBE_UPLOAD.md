# YouTube Upload Guide

This guide walks through setting up YouTube uploads for the Stoic Modernized pipeline.

## Prerequisites

1. **Google Cloud Account** - [Create one for free](https://console.cloud.google.com/)
2. **OAuth2 Credentials** - Downloaded from Google Cloud Console
3. **Python Dependencies** - Install with:
   ```bash
   pip install google-api-python-client google-auth google-auth-oauthlib google-auth-httplib2
   ```

## Setup Steps

### 1. Create Google Cloud Project

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Click "Select a project" → "New Project"
3. Name it "Stoic Modernized" (or any name you prefer)
4. Click "Create"

### 2. Enable YouTube Data API v3

1. In your project, go to **APIs & Services** → **Library**
2. Search for "YouTube Data API v3"
3. Click on it and press **Enable**

### 3. Create OAuth2 Credentials

1. Go to **APIs & Services** → **Credentials**
2. Click **Create Credentials** → **OAuth client ID**
3. If prompted, configure the **OAuth consent screen**:
   - User Type: **External**
   - App name: **Stoic Modernized**
   - User support email: your email
   - Developer contact: your email
   - Click **Save and Continue**
   - Scopes: Skip (we'll add them later)
   - Test users: Add your Google account
   - Click **Save and Continue**

4. Back to **Create OAuth client ID**:
   - Application type: **Desktop app**
   - Name: **Stoic Modernized Desktop**
   - Click **Create**

5. Download the JSON file and save it as `client_secret.json`

### 4. Configure the Application

**Option A: Set in `.env` file**

```env
YOUTUBE_API_KEY=your_api_key_here
YOUTUBE_CREDENTIALS_PATH=/path/to/client_secret.json
YOUTUBE_PRIVACY_STATUS=unlisted
```

**Option B: Use default location**

Place `client_secret.json` in `~/.stoic-modernized/`:
```bash
mkdir -p ~/.stoic-modernized
cp client_secret.json ~/.stoic-modernized/
```

### 5. Authenticate

**Option A: Browser-based authentication (default)**

```bash
python -m src.auth_oauth
```

This will:
1. Open your browser automatically
2. Ask you to sign in with your Google account
3. Request permission to upload videos to YouTube
4. Save the token to `~/.stoic-modernized/oauth2_token.json`

**Option B: Headless authentication (no browser required)**

For servers or environments without a browser:

```bash
python -m src.auth_oauth --headless
```

**Headless flow steps:**

1. **Run the command** - It will display an authorization URL
2. **Open the URL** - Copy and paste it into your browser (or on another device)
3. **Sign in** - Use your Google account
4. **Grant permission** - Allow the app to upload videos to YouTube
5. **Redirect page** - You'll see "Refused to connect" or similar - this is normal
6. **Copy the code** - The URL in your browser's address bar will be very long. Copy everything after `code=`
7. **Paste the code** - Return to the terminal and paste the authorization code

**Example:**

```
Step 1: Open this URL in your browser:
  https://accounts.google.com/o/oauth2/auth?...

Step 2: Sign in with your Google account
Step 3: Grant permission to upload videos to YouTube
Step 4: You'll be redirected to a page that says 'Refused to connect'
Step 5: Copy the entire URL from your browser's address bar
Step 6: Extract the authorization code (the part after 'code=')

Example URL:
  http://localhost/?code=4/0AeanS7a...very_long_code...xyz&scope=...

The code is everything between 'code=' and '&scope=':
  4/0AeanS7a...very_long_code...xyz

Enter the authorization code: 4/0AeanS7a...paste_code_here...xyz

✓ Token saved to: /home/rafatz/.stoic-modernized/oauth2_token.json
```

### 6. Test the Upload

After a successful authentication, you should see:
```
✓ Successfully authenticated!
   Channel: Your Channel Name
   Channel ID: UCxxxxxxxxxxxxxxxxxxx

You can now upload videos using: python -m src.main upload <job_id>
```

## Running the Pipeline

### Full Pipeline (with upload)

```bash
python -m src.main run "Your Video Topic" --provider edge
```

### Pipeline without upload

```bash
python -m src.main run "Your Video Topic" --skip-upload --provider edge
```

### Manual Upload

```bash
# Run through all stages up to metadata
python -m src.main research "Your Topic"
python -m src.main script <job_id>
python -m src.main scene <job_id>
python -m src.main tts <job_id>
python -m src.main images <job_id>
python -m src.main subtitles <job_id>
python -m src.main render <job_id>
python -m src.main metadata <job_id>

# Upload the video
python -m src.main upload <job_id>
```

## Configuration Options

### Privacy Status

Set in `.env`:
```env
YOUTUBE_PRIVACY_STATUS=public    # public, unlisted, or private
```

### Scheduled Upload

Set a future publish time in ISO 8601 format:
```env
YOUTUBE_SCHEDULE_DATETIME=2026-04-10T10:00:00Z
```

The video will be scheduled to publish at that time.

## Troubleshooting

### "OAuth2 token expired"

Run the authentication script again:
```bash
python -m src.auth_oauth
```

### "No OAuth2 token found"

Make sure:
1. You ran `python -m src.auth_oauth` successfully
2. The token file exists at `~/.stoic-modernized/oauth2_token.json`

### "Invalid grant"

This means the token expired or was revoked. Re-authenticate:
```bash
python -m src.auth_oauth
```

### "API key not configured"

The upload requires OAuth2, not just an API key. Make sure you:
1. Have OAuth2 credentials set up
2. Ran the authentication script

### Dependencies missing

Install the required packages:
```bash
pip install google-api-python-client google-auth google-auth-oauthlib google-auth-httplib2
```

## File Locations

- **Credentials file**: `~/.stoic-modernized/client_secret.json` (download from Google Cloud)
- **Token file**: `~/.stoic-modernized/oauth2_token.json` (generated by auth script)
- **Video output**: `output/jobs/<job_id>/final.mp4`
- **Thumbnail**: `output/jobs/<job_id>/thumbnail.png`
- **Metadata**: `output/jobs/<job_id>/metadata/metadata.json`

## Next Steps

After your video is uploaded:
1. Check YouTube Studio for analytics
2. Share the video on social media
3. Plan your next video topic!

---

**Questions or issues?** Check the error messages carefully - they usually tell you exactly what's wrong.
