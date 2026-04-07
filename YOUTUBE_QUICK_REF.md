# YouTube Upload - Quick Reference

## What Was Implemented

### 1. OAuth2 Authentication
- **Script**: `src/auth_oauth.py`
- **Usage**: `python -m src.auth_oauth` (browser) or `python -m src.auth_oauth --headless` (no browser)
- **Purpose**: Authorize the app to upload videos to your YouTube channel
- **Output**: Creates `~/.stoic-modernized/oauth2_token.json`

### 2. YouTube Uploader
- **Module**: `src/stages/upload.py`
- **Features**:
  - OAuth2 authentication
  - Video upload with metadata
  - Thumbnail upload
  - Scheduled uploads
  - Privacy status support (public/unlisted/private)
  - Retry logic for failed uploads

### 3. Dependencies Added
- `google-api-python-client`
- `google-auth`
- `google-auth-oauthlib`
- `google-auth-httplib2`

### 4. Configuration
Added to `src/config.py`:
- `youtube_credentials_path` - Path to OAuth2 credentials JSON

### 5. CLI Integration
Updated `src/main.py`:
- `metadata` command now uses real uploader (not mock)
- `upload` command shows helpful error messages and instructions

### 6. Documentation
- `YOUTUBE_UPLOAD.md` - Complete setup guide
- `README.md` - Updated with YouTube upload section

## Files Created/Modified

**Created:**
- `src/auth_oauth.py` - OAuth2 authentication script
- `YOUTUBE_UPLOAD.md` - Setup guide
- `YOUTUBE_QUICK_REF.md` - Quick reference

**Modified:**
- `src/stages/upload.py` - Real YouTube upload implementation
- `src/main.py` - CLI commands updated
- `src/config.py` - Added credentials path setting
- `pyproject.toml` - Added OAuth2 dependencies
- `README.md` - YouTube upload section added

## How to Use

### Step 1: Install Dependencies
```bash
cd /home/rafatz/projects/stoic-modernized
source .venv/bin/activate
pip install google-api-python-client google-auth google-auth-oauthlib google-auth-httplib2
```

### Step 2: Download OAuth2 Credentials
1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a project (or select existing)
3. Enable "YouTube Data API v3"
4. Create OAuth 2.0 credentials (Desktop app)
5. Download JSON file

### Step 3: Save Credentials
```bash
# Option A: Place in default location
cp client_secret.json ~/.stoic-modernized/

# Option B: Set in .env
echo "YOUTUBE_CREDENTIALS_PATH=/path/to/client_secret.json" >> .env
```

### Step 4: Authenticate

**Browser-based (default):**
```bash
python -m src.auth_oauth
```

**Headless (no browser):**
```bash
python -m src.auth_oauth --headless
```

**Headless flow:**
1. Command displays authorization URL
2. Open URL in browser
3. Sign in and grant permission
4. See "Refused to connect" - this is normal
5. Copy the URL from address bar
6. Extract the code (everything after `code=`)
7. Paste code back to terminal
8. Token saved to `~/.stoic-modernized/oauth2_token.json`

### Step 5: Run Pipeline
```bash
# Full pipeline with upload
python -m src.main run "Your Topic" --provider edge

# Or run stages manually
python -m src.main research "Your Topic"
python -m src.main script <job_id>
python -m src.main scene <job_id>
python -m src.main tts <job_id>
python -m src.main images <job_id>
python -m src.main subtitles <job_id>
python -m src.main render <job_id>
python -m src.main metadata <job_id>
python -m src.main upload <job_id>
```

## Configuration Options

### Privacy Status
```env
YOUTUBE_PRIVACY_STATUS=public  # public, unlisted, or private
```

### Scheduled Upload
```env
YOUTUBE_SCHEDULE_DATETIME=2026-04-10T10:00:00Z
```

## Troubleshooting

**"OAuth2 token expired"**
```bash
python -m src.auth_oauth
```

**"No OAuth2 token found"**
Make sure you ran `python -m src.auth_oauth` successfully.

**"Missing google-auth libraries"**
```bash
pip install google-api-python-client google-auth google-auth-oauthlib google-auth-httplib2
```

**"Refused to connect" during headless auth**
This is normal! Just copy the URL from your browser's address bar and extract the code.

## Next Steps

1. ✅ Install OAuth2 dependencies
2. ✅ Download OAuth2 credentials from Google Cloud
3. ⏳ Run `python -m src.auth_oauth` or `python -m src.auth_oauth --headless` to authenticate
4. ⏳ Test with `python -m src.main upload <job_id>`

---

For detailed instructions, see `YOUTUBE_UPLOAD.md`
