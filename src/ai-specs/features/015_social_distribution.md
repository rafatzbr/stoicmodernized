# 015 — Social Distribution

## Overview

The social distribution stage prepares and publishes rendered short-form videos to TikTok, Instagram Reels, and Facebook Reels. It is API-first: Meta Graph API for Instagram/Facebook and TikTok Content Posting API for TikTok. Android/Appium automation remains a fallback for assisted/manual workflows, not the primary production path.

## Architecture

```
render + metadata
      │
      ▼
SocialDistributionStage
 ├─ build_social_captions(metadata)
 ├─ validate platform credentials
 ├─ publish Instagram Reel through Meta Graph API
 ├─ publish Facebook Reel through Meta Graph API
 ├─ submit TikTok Direct Post through Content Posting API
 └─ write distribution/social_uploads.json
```

**Key class:** `SocialDistributionStage` in `src/stages/social_distribution.py`

## CLI

```bash
python -m src.main distribute <job-id> --mock
python -m src.main distribute <job-id> --platforms instagram,facebook
python -m src.main run "topic" --distribute-social --social-mock
```

## Business Rules

- Mock mode never calls external social APIs and writes a full manifest for review.
- Real mode reports `missing_credentials` per platform instead of attempting uploads with incomplete config.
- Captions strip YouTube-only boilerplate such as resource links and subscription copy.
- Captions are platform-specific but derived from the same metadata so posts remain consistent.
- Real TikTok and Instagram pull-from-URL publishing require `SOCIAL_VIDEO_PUBLIC_BASE_URL` to point at a public HTTPS location where the MP4 can be fetched.
- Do not use emulator automation for unattended production posting unless the official API path is unavailable and Rafael explicitly approves the risk.

## Configuration

| Config Key | Purpose |
|------------|---------|
| `SOCIAL_DISTRIBUTION_ENABLED` | Opt-in gate for automatic distribution |
| `SOCIAL_DISTRIBUTION_PLATFORMS` | Comma-separated enabled platforms |
| `META_GRAPH_API_VERSION` | Meta Graph API version |
| `META_APP_ID` / `META_APP_SECRET` | Optional Meta app credentials for automatic long-lived token exchange before publishing |
| `META_PAGE_ACCESS_TOKEN` | Meta Page token used by Instagram/Facebook publishing |
| `INSTAGRAM_USER_ID` | Instagram Professional account ID |
| `FACEBOOK_PAGE_ID` | Facebook Page ID |
| `SOCIAL_VIDEO_PUBLIC_BASE_URL` | Public HTTPS base URL for pull-from-URL video uploads |
| `TIKTOK_ACCESS_TOKEN` | TikTok Content Posting API OAuth token |
| `TIKTOK_PRIVACY_LEVEL` | TikTok post privacy level; defaults to `SELF_ONLY` |

## Output

`output/jobs/<job-id>/distribution/social_uploads.json`

Fields:
- `job_id`
- `status`
- `video_path`
- `metadata_path`
- `captions`
- `platforms[]` with platform status, IDs/URLs, or missing credential errors

## Setup Checklist

1. Convert Instagram to Professional account and connect it to the Facebook Page.
2. Create/configure a Meta developer app and complete required app review for content publishing permissions.
3. Create/configure a TikTok developer app and request Content Posting API access/scopes.
4. Provide a short-lived or durable public HTTPS hosting path for rendered MP4s, or extend the stage with resumable/local upload flows where supported.
5. Add credentials to `.env` or process environment; never commit real tokens.
6. Run `python -m src.main distribute <job-id> --mock`, inspect the manifest, then run real distribution.
