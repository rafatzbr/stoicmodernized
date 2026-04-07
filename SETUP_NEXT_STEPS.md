# YouTube Upload Setup - Next Steps

Your credentials file is ready at: `~/.stoic-modernized/client_secret.json` ✓

## Complete the Setup

### Option 1: Browser Authentication (Easiest)

```bash
cd /home/rafatz/projects/stoic-modernized
source .venv/bin/activate
python -m src.auth_oauth
```

This will open your browser and handle everything automatically.

### Option 2: Headless Authentication (No Browser)

```bash
cd /home/rafatz/projects/stoic-modernized
source .venv/bin/activate
python -m src.auth_oauth --headless
```

**What to do:**
1. Copy the URL it displays
2. Paste into your browser
3. Sign in with your Google account
4. Grant permission to upload videos
5. You'll see "Refused to connect" - this is normal!
6. Copy the entire URL from your browser's address bar
7. Extract the authorization code (everything after `code=` and before `&scope=`)
8. Paste the code back to the terminal

**Example:**
If your URL is:
```
http://localhost/?code=4/0AeanS7a_long_code_here_xyz&scope=https://www.googleapis.com/auth/youtube.upload&state=...
```

The code is:
```
4/0AeanS7a_long_code_here_xyz
```

## After Authentication

You should see:
```
✓ Successfully authenticated!
   Channel: Your Channel Name
   Channel ID: UCxxxxxxxxxxxxxxxxxxx

You can now upload videos using: python -m src.main upload <job_id>
```

## Test It Out

Once authenticated, test with a real video:

```bash
# Run a complete pipeline
python -m src.main run "Stoic philosophy for workplace stress" --provider edge

# Or run stages manually and upload when done
python -m src.main research "Your topic"
python -m src.main script <job_id>
# ... continue with all stages ...
python -m src.main upload <job_id>
```

## Files to Remember

- **Credentials**: `~/.stoic-modernized/client_secret.json` (already in place)
- **Token**: `~/.stoic-modernized/oauth2_token.json` (created after auth)
- **Video output**: `output/jobs/<job_id>/final.mp4`
- **Documentation**: `YOUTUBE_UPLOAD.md` (full guide), `YOUTUBE_QUICK_REF.md` (quick reference)

---

**Questions?** Check the detailed guide at `YOUTUBE_UPLOAD.md`
