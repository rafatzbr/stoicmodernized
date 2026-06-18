"""Cross-platform short-form distribution stage.

The stage is intentionally API-first:
- Instagram Reels and Facebook Reels use Meta Graph API configuration.
- TikTok uses TikTok Content Posting API configuration.
- Mock/dry-run mode writes the same auditable manifest without external calls.
"""

from __future__ import annotations

import html
import json
import re
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import requests

from scripts.generate_social_public_explorer import ensure_channel_links, generate_explorer
from src.config import ENV_FILE, settings
from src.utils import load_json, save_json

SUPPORTED_PLATFORMS = ("instagram", "facebook", "tiktok")

CANONICAL_HASHTAGS = {
    "stoicism": "#Stoicism",
    "stoicmodernized": "#StoicModernized",
    "workplacestress": "#WorkplaceStress",
    "careeradvice": "#CareerAdvice",
    "selfcontrol": "#SelfControl",
    "workanxiety": "#WorkAnxiety",
    "stopspiraling": "#StopSpiraling",
}


def _strip_youtube_boilerplate(description: str) -> str:
    body = str(description or "")
    body = body.split("\n\nResources:", 1)[0]
    body = re.sub(r"Subscribe to @stoic-modernized[^.#!?]*(?:[.!?]|$)", "", body, flags=re.IGNORECASE)
    body = re.sub(r"Watch on YouTube:?\s*\S*", "", body, flags=re.IGNORECASE)
    # YouTube descriptions often include their own hashtag tail. Social captions
    # build a fresh capped/relevance-filtered hashtag set, so strip existing
    # hashtags from the body first to avoid publishing duplicate/over-limit tags.
    body = re.sub(r"(?:^|\s)#\w+", "", body)
    body = re.sub(r"\s+", " ", body).strip(" -")
    return body


def _hashtag(value: str) -> str | None:
    words = re.findall(r"[A-Za-z0-9]+", str(value or ""))
    if not words:
        return None
    compact = "".join(words).lower()
    if compact in CANONICAL_HASHTAGS:
        return CANONICAL_HASHTAGS[compact]
    stopwords = {"a", "an", "and", "at", "for", "of", "or", "the", "to", "you", "your"}
    words = [word for word in words if word.lower() not in stopwords] or words
    tag = "#" + "".join(word[:1].upper() + word[1:] for word in words[:4])
    return tag[:32] if len(tag) > 2 else None


def _tag_tokens(value: str) -> set[str]:
    """Return normalized, meaning-bearing tokens for tag relevance checks."""
    tokens = {token.lower() for token in re.findall(r"[A-Za-z0-9]+", str(value or ""))}
    normalized: set[str] = set()
    for token in tokens:
        if token in {"a", "an", "and", "at", "for", "from", "in", "of", "on", "or", "the", "to", "you", "your"}:
            continue
        if token in {"workplace", "working"}:
            token = "work"
        elif token.endswith("ies") and len(token) > 4:
            token = token[:-3] + "y"
        elif token.endswith("ing") and len(token) > 5:
            token = token[:-3]
        elif token.endswith("s") and len(token) > 4:
            token = token[:-1]
        normalized.add(token)
    return normalized


def _hashtags_from_tags(tags: list[Any], context_text: str = "", preferred_tags: list[str] | None = None) -> list[str]:
    context_tokens = _tag_tokens(context_text)
    generic_context_tokens = {"stoic", "stoicism", "modernized"}
    weak_context_tokens = {"work", "job", "office", "career"}
    out: list[str] = []
    seen: set[str] = set()

    def add(item: str) -> None:
        tag = _hashtag(item)
        if not tag:
            return
        key = tag.lower()
        if key in seen:
            return
        seen.add(key)
        out.append(tag)

    # Keep one broad philosophy tag and the channel tag; both are relevant to this channel.
    add("Stoicism")
    add("StoicModernized")

    # YouTube metadata descriptions already carry the approved five-tag tail.
    # Strip those tags from the caption body, but preserve them as high-priority
    # social tags so the media manager does not collapse to only the two defaults.
    for item in preferred_tags or []:
        add(item)
        if len(out) >= 5:
            return out[:5]

    for item in [str(tag) for tag in tags]:
        item_tokens = _tag_tokens(item)
        if not item_tokens:
            continue
        distinctive_tokens = item_tokens - generic_context_tokens - weak_context_tokens
        if distinctive_tokens and not (distinctive_tokens & context_tokens):
            continue
        if not distinctive_tokens and not (item_tokens & context_tokens):
            continue
        add(item)
        if len(out) >= 5:
            break
    return out[:5]


def _truncate_at_word(text: str, limit: int) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= limit:
        return text
    return text[: limit - 3].rsplit(" ", 1)[0].rstrip(" ,;:-") + "..."


def _metadata_display_title(raw_title: str, channel_name: str) -> str:
    title = str(raw_title or "Untitled Video").strip()
    suffixes = {
        f" | {channel_name}",
        f" - {channel_name}",
        " | Scam Drills",
        " - Scam Drills",
        " | Stoic Modernized",
        " - Stoic Modernized",
        " | The AI Signal",
        " - The AI Signal",
    }
    for suffix in suffixes:
        if title.endswith(suffix):
            return title[: -len(suffix)].strip()
    return title


def channel_slug() -> str:
    channel = getattr(settings, "default_channel", "stoic-modernized")
    return str(getattr(channel, "value", channel))


def media_explorer_public_root() -> Path:
    configured = getattr(settings, "media_explorer_public_root", None)
    if configured:
        return Path(configured).expanduser()
    default_jobs_dir = settings.project_root / "output" / "jobs"
    if settings.project_root.name == "scam-drills" and settings.jobs_dir == default_jobs_dir:
        return settings.project_root.parent / "stoic-modernized" / "output" / "social_public"
    return settings.jobs_dir.parent / "social_public"


def channel_job_roots() -> dict[str, Path]:
    roots = {
        "stoic-modernized": settings.project_root.parent / "stoic-modernized" / "output" / "jobs",
        "scam-drills": settings.project_root.parent / "scam-drills" / "output" / "jobs",
    }
    roots[channel_slug()] = settings.jobs_dir
    return roots


def build_social_captions(metadata: dict[str, Any], channel_name: str = "Stoic Modernized") -> dict[str, str]:
    """Build platform-specific captions from YouTube metadata.

    Captions intentionally remove YouTube-only boilerplate/resources and keep a
    compact Shorts/Reels/TikTok-friendly body plus a small hashtag set.
    """
    raw_description = str(metadata.get("description") or "")
    raw_title = _metadata_display_title(str(metadata.get("title") or "Untitled Video"), channel_name)
    body = _strip_youtube_boilerplate(raw_description) or raw_title
    raw_tags = metadata.get("tags")
    tags: list[Any] = raw_tags if isinstance(raw_tags, list) else []
    description_hashtags = re.findall(r"(?<!\w)#\w+", raw_description)
    hashtags = _hashtags_from_tags(tags, context_text=f"{raw_title} {body}", preferred_tags=description_hashtags)
    hashtag_tail = " ".join(hashtags)

    short_body = _truncate_at_word(body, 180)
    medium_body = _truncate_at_word(body, 420)
    title_lead = _truncate_at_word(raw_title, 90)

    return {
        "tiktok": _truncate_at_word(f"{short_body} {hashtag_tail}".strip(), 2200),
        "instagram": _truncate_at_word(f"{title_lead}\n\n{medium_body}\n\n{hashtag_tail}".strip(), 2200),
        "facebook": _truncate_at_word(f"{medium_body}\n\n{hashtag_tail}".strip(), 5000),
    }


def public_media_url(job_id: str, filename: str, slug: str | None = None) -> str | None:
    """Return the public HTTPS URL for a staged social_public job artifact."""
    base_url = settings.social_video_public_base_url
    if not base_url:
        return None
    return f"{base_url.rstrip('/')}/{slug or channel_slug()}/{job_id}/{filename}"


def publish_media_explorer_artifacts(
    job_id: str,
    video_path: str | Path,
    metadata: dict[str, Any],
    captions: dict[str, str] | None = None,
) -> dict[str, str | Path | None]:
    """Stage a rendered MP4 and helper page into output/social_public and refresh videos.html.

    This is intentionally separate from social API publishing so normal video
    generation jobs always leave a browsable/reviewable artifact at the public
    Stoic Modernized media origin.
    """
    source_video_path = Path(video_path)
    if not source_video_path.exists():
        raise FileNotFoundError(f"Rendered video not found for media explorer publish: {source_video_path}")

    captions = captions or build_social_captions(metadata, channel_name=settings.channel_name)
    slug = channel_slug()
    public_root = media_explorer_public_root()
    ensure_channel_links(public_root=public_root, channel_job_roots=channel_job_roots())
    public_dir = settings.jobs_dir / job_id
    public_dir.mkdir(parents=True, exist_ok=True)

    public_video_path = public_dir / source_video_path.name
    if source_video_path.resolve() != public_video_path.resolve():
        shutil.copy2(source_video_path, public_video_path)

    title = _metadata_display_title(str(metadata.get("title") or "Untitled Video"), settings.channel_name)
    description = captions.get("instagram") or _strip_youtube_boilerplate(str(metadata.get("description") or "")) or title
    public_video_url = public_media_url(job_id, public_video_path.name, slug=slug)
    public_page_url = f"{settings.social_video_public_base_url.rstrip('/')}/{slug}/{job_id}/" if settings.social_video_public_base_url else None
    page_path = public_dir / "index.html"
    page_path.write_text(
        _render_instagram_upload_page(
            title=title,
            description=description,
            video_filename=public_video_path.name,
            public_video_url=public_video_url or public_video_path.name,
            job_id=job_id,
        ),
        encoding="utf-8",
    )
    explorer_path = generate_explorer(public_root=public_root, channel_job_roots=channel_job_roots())
    return {
        "path": page_path,
        "url": public_page_url,
        "public_video_path": public_video_path,
        "public_video_url": public_video_url,
        "explorer_path": explorer_path,
    }


class SocialDistributionStage:
    """Distribute a rendered short video to TikTok, Instagram Reels, and Facebook Reels."""

    def __init__(self, job_id: str, mock: bool = False, platforms: list[str] | None = None) -> None:
        self.job_id = job_id
        self.mock = mock or settings.mock_mode
        self.platforms = platforms or self._configured_platforms()
        self.job_dir = settings.jobs_dir / job_id
        self.distribution_dir = self.job_dir / "distribution"

    def _configured_platforms(self) -> list[str]:
        configured = str(settings.social_distribution_platforms or ",".join(SUPPORTED_PLATFORMS))
        platforms = [item.strip().lower() for item in configured.split(",") if item.strip()]
        return [platform for platform in platforms if platform in SUPPORTED_PLATFORMS]

    def run(self) -> dict[str, Any]:
        metadata = self._load_metadata()
        video_path = self._resolve_video_path()
        captions = build_social_captions(metadata, channel_name=settings.channel_name)
        manual_page = self._write_instagram_manual_upload_page(video_path, metadata, captions)

        platform_results = []
        for platform in self.platforms:
            if self.mock:
                platform_results.append(self._mock_platform_result(platform, captions[platform]))
            elif platform == "instagram":
                platform_results.append(self._publish_instagram_reel(video_path, captions[platform]))
            elif platform == "facebook":
                platform_results.append(self._publish_facebook_reel(video_path, captions[platform]))
            elif platform == "tiktok":
                platform_results.append(self._publish_tiktok(video_path, captions[platform]))

        public_video_url = self._public_video_url(video_path)
        status = self._aggregate_status(platform_results)
        manifest = {
            "job_id": self.job_id,
            "status": status,
            "generated_at": datetime.now(UTC).isoformat(),
            "video_path": str(video_path),
            "public_video_url": public_video_url,
            "manual_instagram_page_path": str(manual_page["path"]),
            "manual_instagram_page_url": manual_page["url"],
            "metadata_path": str(self.job_dir / "metadata" / "metadata.json"),
            "captions": captions,
            "platforms": platform_results,
        }
        self.save_manifest(manifest)
        return manifest

    def save_manifest(self, manifest: dict[str, Any]) -> Path:
        self.distribution_dir.mkdir(parents=True, exist_ok=True)
        path = self.distribution_dir / "social_uploads.json"
        save_json(manifest, path)
        return path

    def _load_metadata(self) -> dict[str, Any]:
        path = self.job_dir / "metadata" / "metadata.json"
        if not path.exists():
            raise FileNotFoundError(f"No metadata found for social distribution: {path}")
        return load_json(path)

    def _resolve_video_path(self) -> Path:
        candidates = [
            self.job_dir / "remotion_output.mp4",
            self.job_dir / "rendered.mp4",
            self.job_dir / "video.mp4",
        ]
        for candidate in candidates:
            if candidate.exists():
                return candidate
        raise FileNotFoundError(f"No rendered video found for social distribution in {self.job_dir}")

    def _mock_platform_result(self, platform: str, caption: str) -> dict[str, Any]:
        return {
            "platform": platform,
            "status": "mock_uploaded",
            "post_id": f"mock-{platform}-{self.job_id}",
            "url": f"https://example.com/{platform}/{self.job_id}",
            "caption_preview": caption[:240],
        }

    def _missing_credentials(self, platform: str, missing: list[str]) -> dict[str, Any]:
        return {
            "platform": platform,
            "status": "missing_credentials",
            "error": f"Missing required configuration: {', '.join(missing)}",
        }

    def _aggregate_status(self, platform_results: list[dict[str, Any]]) -> str:
        statuses = {result.get("status") for result in platform_results}
        if statuses == {"mock_uploaded"}:
            return "mock_completed"
        if statuses and all(status in {"published", "submitted", "mock_uploaded"} for status in statuses):
            return "completed"
        if "missing_credentials" in statuses:
            return "needs_configuration"
        if "failed" in statuses:
            return "partial_failed"
        return "completed" if platform_results else "no_platforms"

    def _public_video_url(self, video_path: Path) -> str | None:
        base_url = settings.social_video_public_base_url
        if not base_url:
            return None
        return public_media_url(self.job_id, video_path.name)

    def _social_public_job_dir(self) -> Path:
        return settings.jobs_dir / self.job_id

    def _write_instagram_manual_upload_page(
        self, video_path: Path, metadata: dict[str, Any], captions: dict[str, str]
    ) -> dict[str, str | Path | None]:
        return publish_media_explorer_artifacts(self.job_id, video_path, metadata, captions)

    def _publish_instagram_reel(self, video_path: Path, caption: str) -> dict[str, Any]:
        missing = []
        if not settings.meta_page_access_token:
            missing.append("META_PAGE_ACCESS_TOKEN")
        if not settings.instagram_user_id:
            missing.append("INSTAGRAM_USER_ID")
        public_video_url = self._public_video_url(video_path)
        if not public_video_url:
            missing.append("SOCIAL_VIDEO_PUBLIC_BASE_URL")
        if missing:
            return self._missing_credentials("instagram", missing)
        try:
            graph = f"https://graph.facebook.com/{settings.meta_graph_api_version}"
            access_token = self._refresh_meta_access_token_if_configured(graph, settings.meta_page_access_token)
            create = requests.post(
                f"{graph}/{settings.instagram_user_id}/media",
                data={
                    "media_type": "REELS",
                    "video_url": public_video_url,
                    "caption": caption,
                    "access_token": access_token,
                },
                timeout=60,
            )
            create.raise_for_status()
            creation_id = create.json().get("id")
            publish = requests.post(
                f"{graph}/{settings.instagram_user_id}/media_publish",
                data={"creation_id": creation_id, "access_token": access_token},
                timeout=60,
            )
            publish.raise_for_status()
            media_id = publish.json().get("id")
            return {"platform": "instagram", "status": "published", "post_id": media_id, "creation_id": creation_id}
        except Exception as exc:
            return {"platform": "instagram", "status": "failed", "error": self._sanitize_meta_error(exc)}

    def _publish_facebook_reel(self, video_path: Path, caption: str) -> dict[str, Any]:
        missing = []
        if not settings.meta_page_access_token:
            missing.append("META_PAGE_ACCESS_TOKEN")
        if not settings.facebook_page_id:
            missing.append("FACEBOOK_PAGE_ID")
        if missing:
            return self._missing_credentials("facebook", missing)
        try:
            graph = f"https://graph.facebook.com/{settings.meta_graph_api_version}"
            user_or_page_token = self._refresh_meta_access_token_if_configured(graph, settings.meta_page_access_token)
            page_token = self._resolve_facebook_page_access_token(graph, user_or_page_token)
            with video_path.open("rb") as source_file:
                upload = requests.post(
                    f"{graph}/{settings.facebook_page_id}/videos",
                    files={"source": source_file},
                    data={
                        "description": caption,
                        "access_token": page_token,
                        "published": "true",
                    },
                    timeout=300,
                )
            upload.raise_for_status()
            video_id = upload.json().get("id")
            return {"platform": "facebook", "status": "published", "post_id": video_id}
        except Exception as exc:
            return {"platform": "facebook", "status": "failed", "error": self._sanitize_meta_error(exc)}

    def _refresh_meta_access_token_if_configured(self, graph: str, token: str | None) -> str:
        """Exchange a valid Meta token for a fresh long-lived token when app config exists.

        Meta cannot resurrect an already-expired token. This method is best-effort: if
        refresh config is absent or Meta declines the exchange, continue with the
        configured token so the platform call returns the authoritative publishing error.
        """
        if not token:
            return ""
        if not settings.meta_app_id or not settings.meta_app_secret:
            return token

        try:
            response = requests.get(
                f"{graph}/oauth/access_token",
                params={
                    "grant_type": "fb_exchange_token",
                    "client_id": settings.meta_app_id,
                    "client_secret": settings.meta_app_secret,
                    "fb_exchange_token": token,
                },
                timeout=30,
            )
            response.raise_for_status()
            refreshed_token = str(response.json().get("access_token") or "")
        except Exception:
            return token

        if not refreshed_token or refreshed_token == token:
            return token

        self._persist_env_value("META_PAGE_ACCESS_TOKEN", refreshed_token)
        settings.meta_page_access_token = refreshed_token
        return refreshed_token

    def _persist_env_value(self, key: str, value: str) -> None:
        env_path = ENV_FILE
        lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []
        replacement = f"{key}={value}"
        for index, line in enumerate(lines):
            if line.startswith(f"{key}="):
                lines[index] = replacement
                break
        else:
            lines.append(replacement)
        env_path.parent.mkdir(parents=True, exist_ok=True)
        env_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")

    def _sanitize_meta_error(self, exc: Exception) -> str:
        text = str(exc)
        text = re.sub(r"access_token=[^&\s\"]+", "access_token=[REDACTED]", text)
        if settings.meta_page_access_token:
            text = text.replace(settings.meta_page_access_token, "[REDACTED]")
        if settings.meta_app_secret:
            text = text.replace(settings.meta_app_secret, "[REDACTED]")
        return text

    def _resolve_facebook_page_access_token(self, graph: str, access_token: str) -> str:
        """Resolve a Page access token even when .env currently holds a user token.

        Meta Business Portfolio setups often expose Pages only through business_management;
        Graph API Explorer may return a user token that can read the Page and expose its
        `access_token`, but cannot POST to /{page-id}/videos directly.
        """
        response = requests.get(
            f"{graph}/{settings.facebook_page_id}",
            params={
                "fields": "access_token",
                "access_token": access_token,
            },
            timeout=30,
        )
        response.raise_for_status()
        page_token = response.json().get("access_token")
        if not page_token:
            raise RuntimeError("Could not resolve Facebook Page access token from configured META_PAGE_ACCESS_TOKEN")
        return page_token

    def _publish_tiktok(self, video_path: Path, caption: str) -> dict[str, Any]:
        missing = []
        if not settings.tiktok_access_token:
            missing.append("TIKTOK_ACCESS_TOKEN")
        public_video_url = self._public_video_url(video_path)
        if not public_video_url:
            missing.append("SOCIAL_VIDEO_PUBLIC_BASE_URL")
        if missing:
            return self._missing_credentials("tiktok", missing)
        try:
            response = requests.post(
                "https://open.tiktokapis.com/v2/post/publish/video/init/",
                headers={
                    "Authorization": f"Bearer {settings.tiktok_access_token}",
                    "Content-Type": "application/json; charset=UTF-8",
                },
                json={
                    "post_info": {
                        "title": caption,
                        "privacy_level": settings.tiktok_privacy_level,
                        "disable_duet": False,
                        "disable_comment": False,
                        "disable_stitch": False,
                    },
                    "source_info": {"source": "PULL_FROM_URL", "video_url": public_video_url},
                },
                timeout=60,
            )
            response.raise_for_status()
            payload = response.json()
            data = payload.get("data") or {}
            return {
                "platform": "tiktok",
                "status": "submitted",
                "publish_id": data.get("publish_id"),
                "upload_url": data.get("upload_url"),
                "raw_status": payload.get("error", {}).get("code") or "ok",
            }
        except Exception as exc:
            return {"platform": "tiktok", "status": "failed", "error": str(exc)}


def _render_instagram_upload_page(
    *, title: str, description: str, video_filename: str, public_video_url: str, job_id: str
) -> str:
    title_html = html.escape(title)
    description_html = html.escape(description)
    video_src = html.escape(video_filename, quote=True)
    public_url_html = html.escape(public_video_url)
    short_job = html.escape(job_id[:8])
    return f'''<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Instagram Upload Kit</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Doto:wght@400;600;700&family=Space+Grotesk:wght@300;400;500;700&family=Space+Mono:wght@400;700&display=swap" rel="stylesheet">
  <style>
    :root {{ --black:#000; --surface:#111; --border:#222; --border-visible:#333; --text-secondary:#999; --text-primary:#E8E8E8; --text-display:#FFF; --accent:#D71921; --success:#4A9E5C; }}
    * {{ box-sizing: border-box; }}
    body {{ margin:0; min-height:100vh; background:radial-gradient(circle at 16px 16px,rgba(255,255,255,.08) 1px,transparent 1px),var(--black); background-size:16px 16px; color:var(--text-primary); font-family:"Space Grotesk",system-ui,sans-serif; }}
    main {{ width:min(1180px,calc(100vw - 32px)); margin:0 auto; padding:48px 0 64px; }}
    .label {{ font-family:"Space Mono",monospace; font-size:11px; letter-spacing:.08em; text-transform:uppercase; color:var(--text-secondary); }}
    .layout {{ display:grid; grid-template-columns:minmax(280px,420px) 1fr; gap:48px; align-items:start; }}
    .video-frame {{ border:1px solid var(--border-visible); background:var(--surface); padding:12px; }}
    video {{ display:block; width:100%; aspect-ratio:9/16; background:#000; }}
    .actions {{ display:grid; gap:8px; margin-top:12px; }}
    a.button, button {{ appearance:none; border:1px solid var(--border-visible); background:transparent; color:var(--text-primary); min-height:44px; padding:0 16px; font-family:"Space Mono",monospace; font-size:12px; letter-spacing:.06em; text-transform:uppercase; text-decoration:none; display:inline-flex; justify-content:center; align-items:center; cursor:pointer; transition:border-color 180ms ease,color 180ms ease,background 180ms ease; }}
    a.button:hover, button:hover {{ border-color:var(--text-display); color:var(--text-display); }}
    button.primary {{ background:var(--text-display); color:var(--black); border-color:var(--text-display); }}
    button.primary:hover {{ background:var(--accent); border-color:var(--accent); color:var(--text-display); }}
    .panel {{ border-top:1px solid var(--border-visible); padding-top:18px; margin-bottom:42px; }}
    .panel-header {{ display:flex; justify-content:space-between; gap:24px; margin-bottom:12px; align-items:baseline; }}
    .field {{ background:var(--surface); border:1px solid var(--border); padding:18px; color:var(--text-primary); font-size:18px; line-height:1.45; white-space:pre-wrap; word-break:break-word; }}
    .title-field {{ font-size:clamp(24px,4vw,38px); line-height:1.1; color:var(--text-display); letter-spacing:-.02em; }}
    .meta-grid {{ display:grid; grid-template-columns:repeat(3,1fr); gap:16px; margin-top:48px; }}
    .meta-card {{ border:1px solid var(--border); padding:16px; background:rgba(17,17,17,.72); }}
    .meta-value {{ display:block; margin-top:8px; font-family:"Space Mono",monospace; color:var(--text-display); font-size:14px; word-break:break-all; }}
    .copy-state {{ min-height:18px; margin-top:12px; color:var(--success); font-family:"Space Mono",monospace; font-size:11px; letter-spacing:.08em; text-transform:uppercase; }}
    @media (max-width:820px) {{ main {{ padding-top:32px; }} .layout {{ grid-template-columns:1fr; }} .video-frame {{ max-width:420px; }} .meta-grid {{ grid-template-columns:1fr; }} }}
  </style>
</head>
<body>
  <main>
    <section class="layout" aria-label="Instagram upload assets">
      <aside>
        <div class="video-frame">
          <video controls playsinline preload="metadata" src="{video_src}"></video>
          <div class="actions">
            <a class="button" href="{video_src}" download>Download MP4</a>
            <button type="button" class="primary" data-copy="url">Copy Public Video URL</button>
          </div>
        </div>
      </aside>
      <section>
        <div class="panel">
          <div class="panel-header"><div class="label">01 · Title</div><button type="button" data-copy="title">Copy Title</button></div>
          <div id="title" class="field title-field">{title_html}</div><div id="title-state" class="copy-state"></div>
        </div>
        <div class="panel">
          <div class="panel-header"><div class="label">02 · Description / Caption</div><button type="button" data-copy="description">Copy Description</button></div>
          <div id="description" class="field">{description_html}</div><div id="description-state" class="copy-state"></div>
        </div>
      </section>
    </section>
    <section class="meta-grid" aria-label="Upload metadata">
      <div class="meta-card"><span class="label">Public URL</span><span id="url" class="meta-value">{public_url_html}</span></div>
      <div class="meta-card"><span class="label">Format</span><span class="meta-value">1080×1920 · MP4</span></div>
      <div class="meta-card"><span class="label">Job</span><span class="meta-value">{short_job}</span></div>
    </section>
  </main>
  <script>
    const values = {{ title: document.getElementById('title').innerText.trim(), description: document.getElementById('description').innerText.trim(), url: document.getElementById('url').innerText.trim() }};
    async function copyValue(key) {{ await navigator.clipboard.writeText(values[key]); const state = document.getElementById(`${{key}}-state`) || document.querySelector('.copy-state'); if (state) {{ const old = state.textContent; state.textContent = '[COPIED]'; setTimeout(() => {{ state.textContent = old || ''; }}, 1400); }} }}
    document.querySelectorAll('[data-copy]').forEach((button) => {{ button.addEventListener('click', () => copyValue(button.dataset.copy)); }});
  </script>
</body>
</html>
'''
