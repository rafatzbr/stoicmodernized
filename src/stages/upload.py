"""YouTube upload stage module."""

import asyncio
import json
import os
import random
import re
from datetime import UTC, datetime
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Optional

from src.config import Channel, settings
from src.models import UploadResult
from src.utils import load_json


TOPIC_FAMILY_ALIASES = {
    "reacting": "react",
    "react": "react",
    "reaction": "react",
    "reactive": "react",
    "reactivity": "react",
    "notifications": "notification",
    "pings": "ping",
    "messages": "message",
    "meetings": "meeting",
    "coworkers": "coworker",
    "bosses": "boss",
    "managers": "boss",
    "manager": "boss",
    "deadlines": "deadline",
    "priorities": "priority",
    "shifts": "shift",
    "shifted": "shift",
    "changes": "change",
    "changed": "change",
    "changing": "change",
    "emergency": "pressure",
    "urgent": "pressure",
    "urgency": "pressure",
    "panic": "pressure",
    "rushing": "rush",
    "rushed": "rush",
    "loops": "loop",
    "replaying": "replay",
    "receipts": "receipt",
    "expenses": "expense",
    "finance": "expense",
    "accounting": "expense",
    "reimbursements": "expense",
    "reimbursement": "expense",
    "charges": "expense",
    "charge": "expense",
    "cards": "expense",
    "card": "expense",
    "ledgers": "expense",
    "ledger": "expense",
}

TOPIC_FAMILY_STOPWORDS = {
    "actually", "after", "again", "always", "ancient", "anything", "around", "because", "before", "being",
    "below", "better", "calm", "can", "comment", "control", "costing", "delay", "every", "fact", "feel",
    "five", "focus", "from", "gets", "good", "have", "instant", "instantly", "just", "keep", "letting",
    "life", "making", "minute", "minutes", "modernized", "more", "need", "next", "normal", "only",
    "power", "practical", "put", "real", "really", "reply", "said", "saying", "scenario", "start", "still",
    "stop", "stoic", "stoicism", "subscribe", "takes", "than", "that", "their", "them", "then", "there",
    "these", "thing", "think", "this", "those", "through", "today", "tools", "urge", "use", "useful",
    "video", "wins", "with", "work", "your", "you",
}

TOPIC_FAMILY_TRIGGER_TOKENS = {
    "slack", "notification", "meeting", "boss", "coworker", "deadline", "burnout", "layoff", "email",
    "text", "ping", "message", "praise", "approval", "disrespect", "overexplaining", "overthinking", "rumination",
    "ruminate", "anxiety", "fear", "stress", "worry", "panic", "politics", "priority", "pressure", "react", "expense", "receipt",
    "waiting", "silence", "reply", "agenda", "phone", "tabs", "scrolling", "inbox", "tired", "exhausted",
    "boundary", "promotion", "raise", "metrics", "recognition", "status", "mistake", "reputation",
    "projector", "crash", "delay", "late", "coffee", "printer", "elevator", "parking",
    "fomo", "layoffs", "reorg", "job", "security", "conflict", "disagreement", "comparison",
    "career", "feedback", "criticism", "review", "ego", "access", "permission", "drive", "link",
    "denied", "import", "workspace", "noise", "credit", "passive", "aggressive", "blame", "gossip",
    "excluded", "interrupt", "interrupted",
}

MAJOR_WORKPLACE_STRESSOR_TOKENS = {
    "fomo", "layoff", "layoffs", "reorg", "job", "security", "conflict", "disagreement",
    "politics", "status", "comparison", "career", "promotion", "feedback", "criticism", "review",
    "reputation", "ego", "coworker", "credit", "passive", "aggressive", "blame", "gossip",
}

# These are useful sentiment/context words, but too broad to prove a repeated subject by
# themselves. They only count when paired with at least one more concrete trigger.
TOPIC_FAMILY_GENERIC_TRIGGER_TOKENS = {
    "meeting", "react", "pressure", "anxiety", "fear", "stress", "worry", "panic", "rumination", "ruminate",
}

TOPIC_UMBRELLA_TOKENS = {
    "conflict_friction": {
        "boss", "reject", "rejected", "refuse", "criticize", "criticism", "interrupt",
        "argument", "politics", "pressure", "meeting", "conflict", "disagreement", "office",
    },
    "coworker_relations": {
        "coworker", "peer", "credit", "disrespect", "blame", "gossip", "excluded", "interrupt",
        "interrupted", "passive", "aggressive", "resentment",
    },
    "uncertainty_waiting": {
        "waiting", "wait", "pending", "silence", "silent", "reply", "response", "email", "agenda",
        "unknown", "decision", "delayed", "delay",
    },
    "loss_of_control": {
        "projector", "crash", "software", "system", "late", "train", "schedule",
        "booked", "booking", "double", "layoff", "layoffs", "reorg", "security",
    },
    "desire_ambition": {
        "promotion", "raise", "metrics", "views", "analytics", "praise", "approval", "title",
        "recognition", "status", "ambition",
    },
    "ego_reputation": {
        "corrected", "correction", "mistake", "public", "ignored", "junior", "reputation",
        "embarrassed", "wrong", "face",
    },
    "distraction_attention": {
        "phone", "notification", "ping", "message", "tabs", "scrolling", "refresh", "inbox",
        "focus", "attention", "feed", "fomo", "career",
    },
    "fatigue_boundaries": {
        "burnout", "tired", "exhausted", "fatigue", "empty", "weekend", "restore", "yes",
        "boundary", "boundaries", "energy", "calendar",
    },
    "everyday_inconvenience": {
        "coffee", "elevator", "parking", "lunch", "printer", "jam", "broken", "slow",
        "line", "queue", "noise",
    },
}

UMBRELLA_BALANCE_WINDOW = 5
UMBRELLA_BALANCE_MAX_SAME = 2

BOSS_PRESSURE_CONTEXT_TOKENS = {
    "meeting",
    "priority",
    "shift",
    "change",
    "deadline",
    "request",
    "update",
    "pressure",
    "rush",
    "overexplaining",
}

# Explicitly blocked topic keywords - these should NEVER appear in daily videos
BLOCKED_TOPIC_KEYWORDS = {
    "slack",  # Too brand-specific, feels like ad copy
}


class YouTubeUploader:
    """Handles YouTube video upload."""

    def __init__(self, api_key: Optional[str] = None, mock: bool = False, channel: Channel = settings.default_channel):
        """Initialize YouTube uploader.

        Args:
            api_key: YouTube Data API key (from env or settings)
            mock: If True, use mock upload
        """
        self.api_key = api_key or settings.youtube_api_key
        self.mock = mock or settings.mock_mode
        # Ensure channel is always a Channel enum, not a string
        if isinstance(channel, str):
            self.channel = Channel(channel)
        else:
            self.channel = channel
        self.privacy_status = settings.youtube_privacy_status.value
        self.schedule_datetime = settings.youtube_schedule_datetime

    async def upload(
        self,
        video_path: str,
        metadata: dict,
        thumbnail_path: Optional[str] = None,
        job_dir: Optional[str] = None,
    ) -> UploadResult:
        """Upload video to YouTube.

        Args:
            video_path: Path to video file
            metadata: YouTube metadata (title, description, tags, etc.)
            thumbnail_path: Optional path to thumbnail

        Returns:
            UploadResult with upload status and video URL
        """
        # Run all guardrails before upload
        guardrail_error = self._background_music_guardrail(job_dir)
        if guardrail_error:
            return UploadResult(
                video_id=None,
                video_url=None,
                upload_status="blocked",
                error=guardrail_error,
            )

        # Check for duplicates and topic cooldown
        duplicate_error = self._recent_video_duplicate_guardrail(metadata, job_dir)
        if duplicate_error:
            return UploadResult(
                video_id=None,
                video_url=None,
                upload_status="blocked",
                error=duplicate_error,
            )

        if self.mock:
            return await self._mock_upload(video_path, metadata)
        else:
            return await self._real_upload(video_path, metadata, thumbnail_path)

    def _background_music_guardrail(self, job_dir: Optional[str]) -> Optional[str]:
        if settings.youtube_allow_background_music_uploads:
            return None
        if not job_dir:
            return None

        job_dir_path = Path(job_dir)
        render_manifest_path = job_dir_path / "render_manifest.json"
        if render_manifest_path.exists():
            try:
                render_manifest = json.loads(render_manifest_path.read_text())
                if not render_manifest.get("background_music_included"):
                    return None
            except Exception:
                pass

        audio_dir = job_dir_path / "audio"
        if not audio_dir.exists():
            return None

        music_files = [
            audio_dir / "background_music.mp3",
            audio_dir / "background_music.wav",
            audio_dir / "background_music.ogg",
            audio_dir / "background_music.m4a",
        ]
        has_background_music = any(path.exists() for path in music_files)
        if not has_background_music:
            return None

        details = ""
        metadata_path = audio_dir / "background_music.json"
        if metadata_path.exists():
            try:
                payload = json.loads(metadata_path.read_text())
                track = payload.get("track") or {}
                title = track.get("title") or "unknown"
                artist = track.get("artist") or "unknown"
                provider = payload.get("provider") or "unknown"
                approved = bool(payload.get("approved_for_youtube"))
                instrumental = bool(payload.get("instrumental"))
                low_background = bool(payload.get("low_background"))
                if provider == "curated" and approved and instrumental and low_background:
                    return None
                details = f" Detected track: {title} by {artist} ({provider})."
            except Exception:
                pass

        return (
            "Upload blocked by music safety guardrail: background music is present but not from the approved curated library." + details +
            " Remove the background track or replace it with a curated approved instrumental track."
        )

    def validate_script_for_generation(self, metadata: dict[str, Any], job_dir: Optional[str]) -> Optional[str]:
        """Validate the finished script/title before expensive media generation.

        This reuses the same duplicate/same-month subject guardrail as upload, but is
        intended to run immediately after script generation and before scene, TTS,
        image generation, subtitles, render, or upload work.
        """
        return self._recent_video_duplicate_guardrail(metadata, job_dir)

    def _recent_video_duplicate_guardrail(self, metadata: dict[str, Any], job_dir: Optional[str], recent_limit: int = 5) -> Optional[str]:
        if not job_dir:
            return None

        current_job_dir = Path(job_dir).resolve()
        current_title = self._normalize_video_text(str(metadata.get("title") or ""))
        current_script = self._load_job_script_text(current_job_dir)
        current_title_tokens = self._video_similarity_tokens(current_title)
        current_script_tokens = self._video_similarity_tokens(current_script)
        current_combined_tokens = self._video_similarity_tokens(f"{current_title} {current_script}")
        current_family_tokens = self._topic_family_tokens(f"{current_title} {current_script}")

        if len(current_combined_tokens) < 4:
            return None

        subject_artifacts = self._recent_subject_artifacts()
        umbrella_error = self._umbrella_balance_guardrail(
            current_family_tokens, subject_artifacts, current_job_dir, "Upload"
        )
        if umbrella_error:
            return umbrella_error

        checked_jobs = 0
        for metadata_path, other_metadata in subject_artifacts:
            other_job_dir = metadata_path.parent.parent.resolve()
            if other_job_dir == current_job_dir:
                continue

            if not self._job_matches_channel(other_job_dir):
                continue

            other_title = self._normalize_video_text(str(other_metadata.get("title") or ""))
            other_script = self._load_job_script_text(other_job_dir)
            other_title_tokens = self._video_similarity_tokens(other_title)
            other_script_tokens = self._video_similarity_tokens(other_script)
            other_combined_tokens = self._video_similarity_tokens(f"{other_title} {other_script}")
            other_family_tokens = self._topic_family_tokens(f"{other_title} {other_script}")

            if not other_combined_tokens:
                continue

            title_ratio = SequenceMatcher(None, current_title, other_title).ratio()
            title_overlap = self._token_jaccard(current_title_tokens, other_title_tokens)
            script_overlap = self._token_jaccard(current_script_tokens, other_script_tokens)
            combined_overlap = self._token_jaccard(current_combined_tokens, other_combined_tokens)

            is_duplicate = (
                (title_ratio >= 0.82 and title_overlap >= 0.7 and combined_overlap >= 0.18)
                or (title_ratio >= 0.78 and (script_overlap >= 0.18 or combined_overlap >= 0.24))
                or (title_overlap >= 0.6 and script_overlap >= 0.2)
                or combined_overlap >= 0.4
            )
            if is_duplicate:
                return (
                    "Upload blocked by duplicate-content guardrail: this video is too similar to recent upload "
                    f"'{other_metadata.get('title', other_job_dir.name)}' (job {other_job_dir.name}). "
                    "Regenerate with a meaningfully different angle before publishing."
                )

            # Also check topic cooldown to catch concept-family repeats.
            # Same-calendar-month repeats are stricter than the rolling recent cooldown:
            # the daily pipeline should not publish another video on the same subject
            # family in the same month, even if more than `recent_limit` jobs exist.
            concept_overlap = current_family_tokens & other_family_tokens
            if self._boss_pressure_subject_hit(current_family_tokens, other_family_tokens, metadata_path, other_metadata):
                return (
                    "Upload blocked by boss-pressure subject guardrail: this video repeats a recent boss/manager "
                    f"pressure scenario from '{other_metadata.get('title', other_job_dir.name)}' (job {other_job_dir.name}). "
                    "Regenerate with a different workplace actor and trigger before publishing."
                )
            if self._same_month_subject_hit(concept_overlap, metadata_path, other_metadata):
                subject_signals = concept_overlap & TOPIC_FAMILY_TRIGGER_TOKENS
                overlap_terms = ", ".join(sorted(subject_signals or concept_overlap)[:4])
                return (
                    "Upload blocked by same-month subject guardrail: this video repeats a subject already sent this month from "
                    f"'{other_metadata.get('title', other_job_dir.name)}' (job {other_job_dir.name}). "
                    f"Shared subject signals: {overlap_terms}. Regenerate with a different workplace trigger before publishing."
                )
            if self._concept_cooldown_hit(concept_overlap, metadata_path, other_metadata):
                subject_signals = concept_overlap & TOPIC_FAMILY_TRIGGER_TOKENS
                overlap_terms = ", ".join(sorted(subject_signals or concept_overlap)[:4])
                return (
                    "Upload blocked by topic-cooldown guardrail: this video repeats a recent concept family from "
                    f"'{other_metadata.get('title', other_job_dir.name)}' (job {other_job_dir.name}). "
                    f"Shared topic signals: {overlap_terms}. Regenerate with a different workplace trigger before publishing."
                )

            if not self._recent_subject_window_hit(metadata_path, other_metadata):
                checked_jobs += 1
                if checked_jobs >= recent_limit:
                    break

        return None

    def validate_topic_for_research(self, topic: str, job_dir: Optional[str], recent_limit: int = 5) -> Optional[str]:
        if not job_dir:
            return None

        current_job_dir = Path(job_dir).resolve()
        current_topic = self._normalize_video_text(topic)
        current_topic_tokens = self._video_similarity_tokens(current_topic)
        current_family_tokens = self._topic_family_tokens(current_topic)

        # Check against explicitly blocked keywords
        for blocked in BLOCKED_TOPIC_KEYWORDS:
            if blocked in current_topic:
                return f"Research blocked: topic contains explicitly blocked keyword '{blocked}'. Choose a different angle."

        if len(current_topic_tokens) < 2:
            return None

        subject_artifacts = self._recent_subject_artifacts()
        umbrella_error = self._umbrella_balance_guardrail(
            current_family_tokens, subject_artifacts, current_job_dir, "Research"
        )
        if umbrella_error:
            return umbrella_error

        checked_jobs = 0
        for metadata_path, other_metadata in subject_artifacts:
            other_job_dir = metadata_path.parent.parent.resolve()
            if other_job_dir == current_job_dir:
                continue
            if not self._job_matches_channel(other_job_dir):
                continue

            other_title = self._normalize_video_text(str(other_metadata.get("title") or ""))
            other_script = self._load_job_script_text(other_job_dir)
            other_combined_text = f"{other_title} {other_script}".strip()
            other_title_tokens = self._video_similarity_tokens(other_title)
            other_combined_tokens = self._video_similarity_tokens(other_combined_text)
            other_family_tokens = self._topic_family_tokens(other_combined_text)

            if not other_combined_tokens:
                continue

            title_ratio = SequenceMatcher(None, current_topic, other_title).ratio()
            title_overlap = self._token_jaccard(current_topic_tokens, other_title_tokens)
            combined_overlap = self._token_jaccard(current_topic_tokens, other_combined_tokens)

            is_duplicate = (
                (title_ratio >= 0.8 and title_overlap >= 0.55)
                or (title_ratio >= 0.72 and combined_overlap >= 0.24)
                or combined_overlap >= 0.38
            )
            if is_duplicate:
                return (
                    "Research blocked by duplicate-topic guardrail: this topic is too similar to recent upload "
                    f"'{other_metadata.get('title', other_job_dir.name)}' (job {other_job_dir.name}). "
                    "Pick a meaningfully different angle before continuing."
                )

            concept_overlap = current_family_tokens & other_family_tokens
            if self._boss_pressure_subject_hit(current_family_tokens, other_family_tokens, metadata_path, other_metadata):
                return (
                    "Research blocked by boss-pressure subject guardrail: this topic repeats a recent boss/manager "
                    f"pressure scenario from '{other_metadata.get('title', other_job_dir.name)}' (job {other_job_dir.name}). "
                    "Research a different workplace actor and trigger before continuing."
                )
            if self._same_month_subject_hit(concept_overlap, metadata_path, other_metadata):
                subject_signals = concept_overlap & TOPIC_FAMILY_TRIGGER_TOKENS
                overlap_terms = ", ".join(sorted(subject_signals or concept_overlap)[:4])
                return (
                    "Research blocked by same-month subject guardrail: this topic repeats a subject already sent this month from "
                    f"'{other_metadata.get('title', other_job_dir.name)}' (job {other_job_dir.name}). "
                    f"Shared subject signals: {overlap_terms}. Research a different workplace trigger before continuing."
                )
            if self._concept_cooldown_hit(concept_overlap, metadata_path, other_metadata):
                subject_signals = concept_overlap & TOPIC_FAMILY_TRIGGER_TOKENS
                overlap_terms = ", ".join(sorted(subject_signals or concept_overlap)[:4])
                return (
                    "Research blocked by topic-cooldown guardrail: this topic repeats a recent concept family from "
                    f"'{other_metadata.get('title', other_job_dir.name)}' (job {other_job_dir.name}). "
                    f"Shared topic signals: {overlap_terms}. Research a different workplace trigger before continuing."
                )

            if not self._recent_subject_window_hit(metadata_path, other_metadata):
                checked_jobs += 1
                if checked_jobs >= recent_limit:
                    break

        return None

    def _recent_subject_artifacts(self) -> list[tuple[Path, dict[str, Any]]]:
        """Return one comparable subject artifact per recent job.

        Metadata is the preferred source after a video is packaged/upload-ready, but the
        daily guardrails also need to learn from abandoned retry attempts. Those attempts
        often have only `script.json` or `research.json`, so metadata-only scans let the
        next candidate repeat the same subject before the expensive stages begin.
        """
        artifacts: list[tuple[Path, dict[str, Any]]] = []
        for job_dir in settings.jobs_dir.glob("*"):
            if not job_dir.is_dir():
                continue
            for rel_path in (
                Path("metadata/metadata.json"),
                Path("script/script.json"),
                Path("research/research.json"),
            ):
                path = job_dir / rel_path
                if not path.exists():
                    continue
                try:
                    payload = load_json(path)
                except Exception:
                    break
                if not isinstance(payload, dict):
                    break
                comparable = self._subject_payload_from_artifact(payload, rel_path)
                if comparable.get("title"):
                    artifacts.append((path, comparable))
                break
        return sorted(artifacts, key=lambda item: item[0].stat().st_mtime, reverse=True)

    def _subject_payload_from_artifact(self, payload: dict[str, Any], rel_path: Path) -> dict[str, Any]:
        comparable = dict(payload)
        if rel_path.parts[0] == "script":
            comparable.setdefault("title", payload.get("title"))
            comparable.setdefault("generated_at", payload.get("generated_at") or payload.get("created_at"))
        elif rel_path.parts[0] == "research":
            title = payload.get("topic") or payload.get("title")
            comparable["title"] = title
            comparable.setdefault("generated_at", payload.get("generated_at") or payload.get("created_at"))
        return comparable

    def _job_matches_channel(self, job_dir: Path) -> bool:
        job_json = job_dir / "job.json"
        if not job_json.exists():
            return True
        try:
            payload = load_json(job_json)
        except Exception:
            return True
        return str(payload.get("channel") or settings.default_channel.value) == self.channel.value

    def _load_job_script_text(self, job_dir: Path) -> str:
        script_path = job_dir / "script" / "script.json"
        if not script_path.exists():
            return ""
        try:
            payload = load_json(script_path)
        except Exception:
            return ""
        return str(payload.get("short_version") or payload.get("narration") or payload.get("hook") or "")

    def _normalize_video_text(self, text: str) -> str:
        cleaned = re.sub(r"\|\s*stoic modernized\b", "", text, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s+", " ", cleaned).strip().lower()
        return cleaned

    def _video_similarity_tokens(self, text: str) -> set[str]:
        stopwords = {
            "a", "an", "and", "are", "at", "be", "below", "but", "by", "comment", "for", "from", "how", "if", "in", "into",
            "is", "it", "its", "just", "minute", "minutes", "modernized", "not", "of", "on", "or", "practical", "so",
            "stoic", "stoicism", "subscribe", "that", "the", "this", "to", "today", "tools", "up", "what", "when", "why",
            "with", "work", "your", "you", "five",
        }
        return {
            token
            for token in re.findall(r"[a-z0-9']+", text.lower())
            if len(token) > 2 and token not in stopwords
        }

    def _topic_family_tokens(self, text: str) -> set[str]:
        tokens: set[str] = set()
        for raw_token in re.findall(r"[a-z0-9']+", text.lower()):
            token = raw_token[:-2] if raw_token.endswith("'s") else raw_token
            token = TOPIC_FAMILY_ALIASES.get(token, token)
            if token.endswith("ies") and len(token) > 4:
                token = token[:-3] + "y"
            elif token.endswith("s") and len(token) > 4 and not token.endswith("ss"):
                token = token[:-1]
            if len(token) <= 3 or token in TOPIC_FAMILY_STOPWORDS:
                continue
            tokens.add(token)
        return tokens

    def _topic_umbrellas(self, family_tokens: set[str]) -> set[str]:
        umbrellas: set[str] = set()
        for umbrella, triggers in TOPIC_UMBRELLA_TOKENS.items():
            if family_tokens & triggers:
                umbrellas.add(umbrella)
        return umbrellas

    def _umbrella_balance_guardrail(
        self,
        current_family_tokens: set[str],
        subject_artifacts: list[tuple[Path, dict[str, Any]]],
        current_job_dir: Path,
        prefix: str,
    ) -> Optional[str]:
        """Prevent the daily feed from clustering around one situation type.

        Duplicate checks catch exact subject-family repeats; this catches the broader
        creative rut Rafael flagged, such as too many conflict/logistics videos in a
        short run. A candidate is blocked only when one of its umbrellas already appears
        at least `UMBRELLA_BALANCE_MAX_SAME` times in the recent window.
        """
        current_umbrellas = self._topic_umbrellas(current_family_tokens)
        if not current_umbrellas:
            return None
        # Major modern-work stressors (FOMO, layoffs/reorgs, office politics,
        # status/reputation, conflict) are legitimate Stoic Modernized lanes.
        # Do not globally suppress them just because their broad umbrella was
        # used recently; exact-subject/monthly cooldowns still block true repeats.
        if current_family_tokens & MAJOR_WORKPLACE_STRESSOR_TOKENS:
            return None

        recent_counts = {umbrella: 0 for umbrella in current_umbrellas}
        checked = 0
        recent_examples: dict[str, str] = {}
        for metadata_path, other_metadata in subject_artifacts:
            other_job_dir = metadata_path.parent.parent.resolve()
            if other_job_dir == current_job_dir or not self._job_matches_channel(other_job_dir):
                continue
            if not self._recent_subject_window_hit(metadata_path, other_metadata):
                continue
            other_title = self._normalize_video_text(str(other_metadata.get("title") or ""))
            other_script = self._load_job_script_text(other_job_dir)
            other_umbrellas = self._topic_umbrellas(self._topic_family_tokens(f"{other_title} {other_script}"))
            for umbrella in current_umbrellas & other_umbrellas:
                recent_counts[umbrella] += 1
                recent_examples.setdefault(umbrella, str(other_metadata.get("title") or other_job_dir.name))
            checked += 1
            if checked >= UMBRELLA_BALANCE_WINDOW:
                break

        overused = [
            u
            for u, count in recent_counts.items()
            if count >= UMBRELLA_BALANCE_MAX_SAME and u in {"conflict_friction", "loss_of_control"}
        ]
        if not overused:
            return None

        names = ", ".join(u.replace("_", " ") for u in sorted(overused))
        example = recent_examples.get(overused[0], "a recent video")
        verb = "Research" if prefix == "Research" else "Upload"
        return (
            f"{verb} blocked by subject-umbrella balance guardrail: recent videos already lean on "
            f"{names} situations (for example '{example}'). Choose a different umbrella such as "
            "uncertainty/waiting, distraction/attention, fatigue/boundaries, ambition/desire, "
            "ego/reputation, or everyday inconvenience."
        )

    def _metadata_datetime(self, metadata_path: Path, metadata: Optional[dict[str, Any]] = None) -> datetime | None:
        """Best-effort publication/artifact timestamp for monthly guardrails."""
        payload = metadata
        if payload is None:
            try:
                loaded = load_json(metadata_path)
                payload = loaded if isinstance(loaded, dict) else {}
            except Exception:
                payload = {}
        payload = payload or {}

        candidates: list[Any] = [
            payload.get("uploaded_at"),
            payload.get("published_at"),
            payload.get("generated_at"),
        ]
        steering_context = payload.get("steering_context") if isinstance(payload.get("steering_context"), dict) else {}
        ledger_packet = steering_context.get("ledger_packet") if isinstance(steering_context.get("ledger_packet"), dict) else {}
        candidates.append(ledger_packet.get("generated_at"))

        for value in candidates:
            if not value:
                continue
            try:
                parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            except ValueError:
                continue
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=UTC)
            return parsed.astimezone(UTC)

        script_path = metadata_path.parent.parent / "script" / "script.json"
        if script_path.exists():
            try:
                script_payload = load_json(script_path)
            except Exception:
                script_payload = {}
            for value in [script_payload.get("generated_at"), script_payload.get("created_at")]:
                if not value:
                    continue
                try:
                    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
                except ValueError:
                    continue
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=UTC)
                return parsed.astimezone(UTC)

        try:
            return datetime.fromtimestamp(metadata_path.stat().st_mtime, tz=UTC)
        except OSError:
            return None

    def _metadata_in_current_month(self, metadata_path: Path, metadata: Optional[dict[str, Any]] = None) -> bool:
        """Return True when a prior video metadata artifact belongs to this UTC month."""
        metadata_dt = self._metadata_datetime(metadata_path, metadata)
        if metadata_dt is None:
            return False
        now = datetime.now(UTC)
        return metadata_dt.year == now.year and metadata_dt.month == now.month

    def _repeated_subject_trigger_overlap(self, concept_overlap: set[str]) -> set[str]:
        trigger_overlap = concept_overlap & TOPIC_FAMILY_TRIGGER_TOKENS
        specific_overlap = trigger_overlap - TOPIC_FAMILY_GENERIC_TRIGGER_TOKENS
        if len(specific_overlap) >= 2:
            return trigger_overlap
        if len(specific_overlap) >= 1 and len(trigger_overlap) >= 2:
            return trigger_overlap
        return set()

    def _same_month_subject_hit(
        self,
        concept_overlap: set[str],
        metadata_path: Path,
        metadata: Optional[dict[str, Any]] = None,
    ) -> bool:
        """Block repeated subject families for the whole calendar month.

        This is intentionally stricter than the rolling topic cooldown. A subject repeat
        needs overlapping trigger-level concepts with at least one specific workplace
        trigger, so broad context words like `meeting` + `react` do not block unrelated
        videos.
        """
        if not self._metadata_in_current_month(metadata_path, metadata):
            return False
        return bool(self._repeated_subject_trigger_overlap(concept_overlap))

    def _recent_subject_window_hit(self, metadata_path: Path, metadata: Optional[dict[str, Any]] = None) -> bool:
        """Return true for the strict short-window freshness checks."""
        if self._metadata_in_current_month(metadata_path, metadata):
            return True
        try:
            age = datetime.now(UTC) - datetime.fromtimestamp(metadata_path.stat().st_mtime, tz=UTC)
        except OSError:
            return False
        return age.days < 7

    def _boss_pressure_subject_hit(
        self,
        current_family_tokens: set[str],
        other_family_tokens: set[str],
        metadata_path: Path,
        metadata: Optional[dict[str, Any]] = None,
    ) -> bool:
        """Block repeated boss/manager pressure scripts even when exact triggers differ.

        The regular same-month guardrail requires two overlapping trigger tokens. That
        missed back-to-back scripts where the same actor/pressure frame repeated but one
        script said "emergency meeting" and the next said "priority change". This guard
        treats boss/manager pressure as one subject family only when both sides have the
        boss actor plus a concrete pressure context token, so unrelated boss praise or
        feedback topics are not blocked by the actor word alone.
        """
        if not self._recent_subject_window_hit(metadata_path, metadata):
            return False
        if "boss" not in current_family_tokens or "boss" not in other_family_tokens:
            return False
        current_context = current_family_tokens & BOSS_PRESSURE_CONTEXT_TOKENS
        other_context = other_family_tokens & BOSS_PRESSURE_CONTEXT_TOKENS
        return bool(current_context and other_context)

    def _concept_cooldown_hit(
        self,
        concept_overlap: set[str],
        metadata_path: Path,
        metadata: Optional[dict[str, Any]] = None,
        cooldown_days: int = 7,
    ) -> bool:
        if len(concept_overlap) < 2:
            return False
        trigger_overlap = self._repeated_subject_trigger_overlap(concept_overlap)
        if not trigger_overlap:
            return False
        metadata_dt = self._metadata_datetime(metadata_path, metadata)
        if metadata_dt is None:
            return False
        age = datetime.now(UTC) - metadata_dt
        return age.days < cooldown_days

    def _token_jaccard(self, left: set[str], right: set[str]) -> float:
        if not left or not right:
            return 0.0
        union = left | right
        if not union:
            return 0.0
        return len(left & right) / len(union)

    async def _mock_upload(
        self, video_path: str, metadata: dict
    ) -> UploadResult:
        """Mock video upload."""
        return UploadResult(
            video_id="dQw4w9WgXcQ",
            video_url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            upload_status="completed",
            error=None,
        )

    def _build_youtube_client(self):
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build

        creds = None
        channel_dir = "stoic-modernized"
        token_path = Path(os.path.expanduser(f"~/.stoic-modernized/{channel_dir}/oauth2_token.json"))

        if token_path.exists():
            try:
                creds = Credentials.from_authorized_user_file(
                    str(token_path),
                    scopes=[
                        "https://www.googleapis.com/auth/youtube",
                        "https://www.googleapis.com/auth/youtube.upload",
                    ],
                )
            except Exception as e:
                print(f"[yellow]Token at {token_path} invalid: {e}[/yellow]")

        if not creds:
            raise RuntimeError(
                f"No valid OAuth token for {self.channel.value}. Run: python -m src.auth_oauth --channel {self.channel.value}"
            )

        return build("youtube", "v3", credentials=creds)

    async def _real_upload(
        self,
        video_path: str,
        metadata: dict,
        thumbnail_path: Optional[str] = None,
    ) -> UploadResult:
        """Real YouTube upload using Google API with OAuth2.

        Uses OAuth2 authentication for user authorization to upload videos.
        """
        try:
            from googleapiclient.http import MediaFileUpload

            youtube = self._build_youtube_client()

            # Prepare video metadata
            video_body = {
                "snippet": {
                    "title": metadata.get("title", "Untitled Video"),
                    "description": metadata.get("description", ""),
                    "tags": metadata.get("tags", []),
                    "categoryId": "22",  # People & Blogs
                },
                "status": {
                    "privacyStatus": self.privacy_status,
                    "selfDeclaredMadeForKids": False,
                },
            }

            # Add scheduling if datetime provided
            if self.schedule_datetime:
                from datetime import datetime
                try:
                    schedule_time = datetime.fromisoformat(self.schedule_datetime.replace("Z", "+00:00"))
                    # YouTube schedules publication by combining privacyStatus=private
                    # with a future publishAt value. uploadStatus is read-only and
                    # sending "scheduled" is rejected by the Data API.
                    video_body["status"]["publishAt"] = schedule_time.isoformat()
                except Exception as e:
                    print(f"[yellow]Invalid schedule datetime, publishing immediately:[/yellow] {e}")

            # Upload video with resumable upload
            print(f"[dim]Uploading video: {video_path}[/dim]")
            media = MediaFileUpload(
                video_path,
                chunksize=1024 * 1024 * 10,  # 10MB chunks for faster uploads
                resumable=True
            )

            response = (
                youtube.videos()
                .insert(
                    part="snippet,status",
                    body=video_body,
                    media_body=media
                )
                .execute()
            )

            video_id = response["id"]
            video_url = f"https://www.youtube.com/watch?v={video_id}"

            print(f"[green]✓ Video uploaded: {video_url}[/green]")

            # Upload thumbnail if provided
            if thumbnail_path and os.path.exists(thumbnail_path):
                print(f"[dim]Uploading thumbnail: {thumbnail_path}[/dim]")
                try:
                    youtube.thumbnails().set(
                        videoId=video_id,
                        media_body=MediaFileUpload(thumbnail_path)
                    ).execute()
                    print(f"[green]✓ Thumbnail uploaded[/green]")
                except Exception as e:
                    print(f"[yellow]✗ Thumbnail upload failed: {e}[/yellow]")

            return UploadResult(
                video_id=video_id,
                video_url=video_url,
                upload_status="completed",
                error=None,
            )

        except Exception as e:
            error_msg = str(e)
            print(f"[red]✗ Upload failed: {error_msg}[/red]")

            # Check for specific error types
            if "invalid_grant" in error_msg or "unauthorized" in error_msg.lower():
                return UploadResult(
                    video_id=None,
                    video_url=None,
                    upload_status="failed",
                    error="OAuth2 token expired. Run: python -m src.auth_oauth",
                )

            return UploadResult(
                video_id=None,
                video_url=None,
                upload_status="failed",
                error=error_msg,
            )

    def update_video_metadata(self, video_id: str, metadata: dict) -> dict[str, Any]:
        """Update an already-uploaded YouTube video's snippet metadata."""
        youtube = self._build_youtube_client()
        request = youtube.videos().list(part="snippet,status", id=video_id)
        response = request.execute()
        items = response.get("items") or []
        if not items:
            raise RuntimeError(f"Video not found: {video_id}")
        item = items[0]
        snippet = item.get("snippet") or {}
        status = item.get("status") or {}
        snippet["title"] = metadata.get("title", snippet.get("title", "Untitled Video"))
        snippet["description"] = self._enforce_description_hashtag_cap(
            metadata.get("description", snippet.get("description", ""))
        )
        snippet["tags"] = metadata.get("tags", snippet.get("tags", []))
        body = {"id": video_id, "snippet": snippet, "status": status}
        return youtube.videos().update(part="snippet,status", body=body).execute()

    def generate_metadata(
        self,
        script_title: str,
        chapters: list[dict],
        description_template: Optional[str] = None,
        script_text: Optional[str] = None,
        job_dir: Optional[str] = None,
    ) -> dict:
        """Generate YouTube metadata from script.

        Args:
            script_title: Video title from script
            chapters: List of chapter dicts with title and timestamp
            description_template: Optional description template
            script_text: Optional full script narration for AI description generation
            job_dir: Optional job directory to load research sources from

        Returns:
            Metadata dict ready for upload
        """
        steering_context = self._load_steering_context(job_dir)
        resolved_title = self._resolve_metadata_title(script_title, chapters, script_text, steering_context)

        # Generate tags based on resolved title + script + steering context
        tags = self._generate_tags(resolved_title, script_text, steering_context)

        # Format chapters for YouTube
        formatted_chapters = self._format_chapters(chapters)

        # Generate description (AI-generated if script_text provided, else fallback)
        description = self._generate_description(
            resolved_title, chapters, description_template, script_text, job_dir, steering_context
        )

        # YouTube has a 100 character limit for video titles
        channel_name = settings.get_channel_name(self.channel)
        max_title_len = 100
        title = f"{resolved_title} | {channel_name}"
        if len(title) > max_title_len:
            # Truncate resolved_title to fit
            available_len = max_title_len - len(f" | {channel_name}")
            title = f"{resolved_title[:available_len].rstrip()} | {channel_name}"

        return {
            "title": title,
            "description": description,
            "tags": tags,
            "chapters": formatted_chapters,
            "steering_context": steering_context,
            "privacy_status": self.privacy_status,
            "scheduled_publish_datetime": self.schedule_datetime,
        }


    def _load_steering_context(self, job_dir: Optional[str] = None) -> dict[str, Any]:
        if not job_dir:
            return {"ledger_packet": {}, "whiskers_handoff": {}, "whiskers_brief": {}, "ledger_strategy": {}}
        script_path = Path(job_dir) / "script" / "script.json"
        if not script_path.exists():
            return {"ledger_packet": {}, "whiskers_handoff": {}, "whiskers_brief": {}, "ledger_strategy": {}}
        try:
            payload = load_json(script_path)
        except Exception:
            return {"ledger_packet": {}, "whiskers_handoff": {}, "whiskers_brief": {}, "ledger_strategy": {}}
        steering = payload.get("steering_chain") if isinstance(payload.get("steering_chain"), dict) else {}
        return {
            "ledger_packet": payload.get("ledger_packet") if isinstance(payload.get("ledger_packet"), dict) else steering.get("ledger_packet") or {},
            "whiskers_handoff": payload.get("whiskers_handoff") if isinstance(payload.get("whiskers_handoff"), dict) else steering.get("whiskers_handoff") or {},
            "whiskers_brief": payload.get("whiskers_brief") if isinstance(payload.get("whiskers_brief"), dict) else steering.get("whiskers_brief") or {},
            "ledger_strategy": payload.get("ledger_strategy") if isinstance(payload.get("ledger_strategy"), dict) else steering.get("ledger_strategy") or {},
        }

    def _resolve_metadata_title(
        self,
        script_title: str,
        chapters: list[dict],
        script_text: Optional[str] = None,
        steering_context: Optional[dict[str, Any]] = None,
    ) -> str:
        title = self._limit_youtube_title(script_title or "Untitled Video")
        steering_context = steering_context or {}
        ledger_packet = steering_context.get("ledger_packet") if isinstance(steering_context.get("ledger_packet"), dict) else {}
        ledger_strategy = steering_context.get("ledger_strategy") if isinstance(steering_context.get("ledger_strategy"), dict) else {}
        whiskers_handoff = steering_context.get("whiskers_handoff") if isinstance(steering_context.get("whiskers_handoff"), dict) else {}

        packaging_angle = str(ledger_packet.get("packaging_angle") or ledger_strategy.get("packaging_angle") or "").lower()
        context_text = self._metadata_context_text(title, script_text, steering_context)

        if "identity" not in packaging_angle:
            return title

        if any(term in title.lower() for term in ("anxiety", "stress", "panic", "overthinking", "control", "calm", "approval")):
            return title

        candidate_terms = [
            ("anxiety", ["anxiety", "work anxiety"]),
            ("stress", ["stress", "work stress"]),
            ("panic", ["panic", "panic at work"]),
            ("overthinking", ["overthinking", "overthinking at work"]),
            ("spiral", ["spiraling", "anxiety spiral"]),
            ("control", ["control", "what you can control"]),
        ]
        selected_phrase = ""
        for needle, options in candidate_terms:
            if needle in context_text:
                selected_phrase = options[0]
                break

        viewer_problem = str(whiskers_handoff.get("viewer_problem") or "").lower()
        if not selected_phrase and "anxiety" in viewer_problem:
            selected_phrase = "anxiety"

        if not selected_phrase:
            return title

        lowered_title = title.lower()
        if lowered_title.startswith("why "):
            if " keeps " in lowered_title:
                return self._limit_youtube_title(re.sub(r"^why\s+.*?\s+keeps\s+", f"Why {selected_phrase.title()} Keeps ", title, count=1, flags=re.IGNORECASE))
            return self._limit_youtube_title(f"Why {selected_phrase.title()} Matters at Work")
        if lowered_title.startswith("how "):
            if " to " in lowered_title:
                return self._limit_youtube_title(re.sub(r"^how\s+to\s+", f"How to handle {selected_phrase} ", title, count=1, flags=re.IGNORECASE))
            return self._limit_youtube_title(f"How to Handle {selected_phrase.title()} at Work")
        return self._limit_youtube_title(f"{title}: {selected_phrase.title()}")

    def _limit_youtube_title(self, title: str, max_len: int = 78) -> str:
        title = re.sub(r"\s+", " ", title).strip()
        if len(title) <= max_len:
            return title
        cut = title[:max_len].rsplit(" ", 1)[0].rstrip(" ,:+-")
        return cut or title[:max_len].rstrip(" ,:+-")

    def _metadata_context_text(
        self,
        title: str,
        script_text: Optional[str] = None,
        steering_context: Optional[dict[str, Any]] = None,
    ) -> str:
        steering_context = steering_context or {}
        whiskers_handoff = steering_context.get("whiskers_handoff") if isinstance(steering_context.get("whiskers_handoff"), dict) else {}
        return " ".join(
            part for part in [
                title,
                script_text or "",
                str(whiskers_handoff.get("viewer_problem") or ""),
                str(whiskers_handoff.get("work_scenario") or ""),
            ] if part
        ).lower()

    def _subject_tag_candidates(
        self,
        title: str,
        script_text: Optional[str] = None,
        steering_context: Optional[dict[str, Any]] = None,
    ) -> list[str]:
        combined = self._metadata_context_text(title, script_text, steering_context)
        normalized = combined.lower()
        words_list = re.findall(r"[a-z0-9']+", normalized)
        words = set(words_list)
        title_words = set(re.findall(r"[a-z0-9']+", title.lower()))

        candidates: list[str] = []

        def add_tags(*tags: str) -> None:
            for tag in tags:
                cleaned = " ".join(tag.split()).strip()
                if cleaned and cleaned not in candidates:
                    candidates.append(cleaned)

        def token_count(*tokens: str) -> int:
            return sum(words_list.count(token) for token in tokens)

        def title_has(*tokens: str) -> bool:
            return any(token in title_words for token in tokens)

        def phrase_present(*phrases: str) -> bool:
            return any(phrase in normalized for phrase in phrases)

        meeting_signal = (
            title_has("meeting", "meetings")
            or token_count("meeting", "meetings") >= 2
            or phrase_present("after the meeting", "after a meeting", "bad meeting", "meeting anxiety")
        )
        patience_signal = title_has("patience") or token_count("patience") >= 1
        panic_signal = (
            title_has("panic")
            or token_count("panic") >= 2
            or phrase_present("panic response", "panic at work", "panic spiral")
        )
        notifications_signal = (
            title_has("slack", "notifications", "email")
            or token_count("slack", "notifications", "email") >= 2
            or phrase_present("notification loop", "slack message", "email overload")
        )
        control_signal = (
            title_has("control", "reaction")
            or token_count("control", "reaction", "reactions") >= 2
            or phrase_present("what you can control", "control your reaction", "dichotomy of control")
        )
        judgment_signal = (
            title_has("judgment", "decide", "decision")
            or token_count("judgment", "decide", "decision", "decisions") >= 2
            or phrase_present("wrong call", "choose wisely", "thought discipline")
        )

        if "paper" in words and ("cut" in words or "cuts" in words):
            add_tags("psychological paper cuts", "workplace disrespect", "idea theft at work", "emotional triggers at work")
        if "idea" in words or "ideas" in words:
            add_tags("credit stealing at work", "workplace recognition", "idea theft at work")
        if patience_signal:
            add_tags("strategic patience", "patience at work", "calm under pressure", "decision making at work")
        if "anxiety" in words:
            add_tags("work anxiety", "anxiety at work", "workplace anxiety", "anxiety management")
        if "stress" in words or "burnout" in words:
            add_tags("work stress", "stress management", "stress at work", "burnout recovery")
        if "spiral" in words or "overthinking" in words or "rumination" in words:
            add_tags("overthinking at work", "stop overthinking", "stop spiraling", "mental loops", "workplace rumination", "anxiety spiral")
        if "catastrophic" in words or "catastrophizing" in words:
            add_tags("catastrophic thinking", "catastrophizing", "anxious thoughts")
        if panic_signal:
            add_tags("panic at work", "panic response", "anxious thoughts")
        if notifications_signal:
            add_tags("work notifications", "reactive work", "digital overwhelm", "communication anxiety")
        if control_signal:
            add_tags("dichotomy of control", "what you can control", "stoic control", "control your reaction")
        if "discipline" in words or "willpower" in words or "friction" in words or "habits" in words:
            add_tags("self discipline", "habit friction", "discipline systems", "systems over motivation")
        if "focus" in words or "attention" in words:
            add_tags("focus at work", "calm focus", "attention control", "attention control at work")
        if judgment_signal:
            add_tags("stoic judgment", "thought discipline", "pause before reacting")
        elif "mindset" in words:
            add_tags("stoic mindset", "thought discipline")
        if meeting_signal:
            add_tags("bad meetings", "meeting anxiety", "post-meeting rumination", "meeting resentment")
        if "work" in words and "life" in words:
            add_tags("work life balance", "modern work", "workplace mindset")

        if not candidates:
            title_text = title.lower()
            fallback_pairs = [
                ("anxiety", "work", "anxiety at work"),
                ("stress", "work", "stress at work"),
                ("meeting", "work", "bad meetings"),
                ("focus", "work", "focus at work"),
                ("discipline", "work", "self discipline"),
            ]
            for left, right, phrase in fallback_pairs:
                if left in title_text and right in title_text:
                    add_tags(phrase)

        return candidates[:18]

    def _recent_tag_counts(self, limit: int = 12) -> dict[str, int]:
        counts: dict[str, int] = {}
        metadata_paths = sorted(
            settings.jobs_dir.glob("*/metadata/metadata.json"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )

        seen_jobs = 0
        for metadata_path in metadata_paths:
            if seen_jobs >= limit:
                break

            job_dir = metadata_path.parent.parent
            job_json = job_dir / "job.json"
            if not job_json.exists():
                continue

            try:
                job_data = load_json(job_json)
            except Exception:
                continue

            if str(job_data.get("channel") or settings.default_channel.value) != self.channel.value:
                continue

            try:
                metadata = load_json(metadata_path)
            except Exception:
                continue

            tags = metadata.get("tags")
            if not isinstance(tags, list):
                continue

            for tag in tags:
                cleaned = " ".join(str(tag).split()).strip().lower()
                if cleaned:
                    counts[cleaned] = counts.get(cleaned, 0) + 1
            seen_jobs += 1

        return counts

    def _format_youtube_tag(self, tag: str) -> Optional[str]:
        cleaned = re.sub(r"[^A-Za-z0-9'&+\-/ ]+", " ", str(tag))
        cleaned = " ".join(cleaned.split()).strip().lower()
        if len(cleaned) < 4:
            return None
        if len(cleaned) > 30:
            trimmed = cleaned[:30].rsplit(" ", 1)[0].strip()
            cleaned = trimmed or cleaned[:30].strip()
        return cleaned or None

    def _format_hashtag_slug(self, tag: str) -> Optional[str]:
        words = re.findall(r"[A-Za-z0-9]+", str(tag))
        if not words:
            return None
        stopwords = {"at", "the", "a", "an", "and", "or", "to", "of", "for", "your", "you", "what"}
        kept = [word for word in words if word.lower() not in stopwords]
        if not kept:
            kept = words
        slug = "#" + "".join(word.lower() for word in kept[:4])
        if len(slug) <= 2:
            return None
        if len(slug) > 28:
            slug = slug[:28].rstrip()
        return slug

    def _generate_tags(
        self,
        title: str,
        script_text: Optional[str] = None,
        steering_context: Optional[dict[str, Any]] = None,
    ) -> list[str]:
        """Generate tags based on video title, script, and steering context."""
        base_tags = settings.get_channel_tags(self.channel)
        core_tags = base_tags[:3]
        support_tags = base_tags[3:]

        recent_counts = self._recent_tag_counts()
        subject_tags = self._subject_tag_candidates(title, script_text, steering_context)

        ranked_candidates: list[tuple[int, int, int, str]] = []
        for index, tag in enumerate(subject_tags):
            ranked_candidates.append((0, recent_counts.get(str(tag).strip().lower(), 0), index, str(tag)))
        offset = len(ranked_candidates)
        for index, tag in enumerate(support_tags):
            ranked_candidates.append((1, recent_counts.get(str(tag).strip().lower(), 0), offset + index, str(tag)))

        ranked_candidates.sort(key=lambda item: (item[0], item[1], item[2]))

        tags: list[str] = []
        seen_lower: set[str] = set()
        for tag in core_tags:
            cleaned = self._format_youtube_tag(tag)
            if not cleaned or cleaned in seen_lower:
                continue
            seen_lower.add(cleaned)
            tags.append(cleaned)

        for _, _, _, tag in ranked_candidates:
            cleaned = self._format_youtube_tag(tag)
            if not cleaned or cleaned in seen_lower:
                continue
            word_count = len(cleaned.split())
            if word_count == 1 and cleaned not in {"stoicism"}:
                continue
            if cleaned in {"stoic advice", "stoic habits", "modern work", "workplace mindset"} and len(tags) >= 10:
                continue
            seen_lower.add(cleaned)
            tags.append(cleaned)
            if len(tags) >= 20:
                break

        return tags[:20]

    def _generate_hashtags(
        self,
        title: str,
        script_text: Optional[str] = None,
        steering_context: Optional[dict[str, Any]] = None,
    ) -> str:
        priority_tags = self._subject_tag_candidates(title, script_text, steering_context)
        hashtag_candidates = ["Stoicism", "StoicModernized"] + priority_tags
        hashtags: list[str] = []
        seen: set[str] = set()
        for tag in hashtag_candidates:
            slug = self._format_hashtag_slug(tag)
            if not slug:
                continue
            lowered = slug.lower()
            if lowered in seen:
                continue
            seen.add(lowered)
            hashtags.append(slug)
            if len(hashtags) >= 5:
                break
        return " ".join(hashtags)

    def _enforce_description_hashtag_cap(self, description: str, max_hashtags: int = 5) -> str:
        """Remove extra hashtags from a generated YouTube description.

        The LLM can ignore the prompt and append additional hashtags. Keep the
        first five hashtags in the whole description and strip any later ones so
        every metadata path has the same hard cap.
        """
        kept = 0

        def replace(match: re.Match[str]) -> str:
            nonlocal kept
            kept += 1
            return match.group(0) if kept <= max_hashtags else ""

        capped = re.sub(r"(?<![\w/])#[A-Za-z0-9_]+", replace, str(description or ""))
        capped = re.sub(r"[ \t]{2,}", " ", capped)
        capped = re.sub(r" *\n", "\n", capped)
        capped = re.sub(r"\n{3,}", "\n\n", capped)
        return capped.strip()

    def _format_chapters(self, chapters: list[dict]) -> list[dict]:
        """Format chapters for YouTube metadata.

        Args:
            chapters: List of chapter dicts

        Returns:
            Formatted chapters for YouTube
        """
        return [
            {
                "title": chapter.get("title", ""),
                "timestamp": chapter.get("timestamp", 0),
            }
            for chapter in chapters
        ]

    def _generate_description(
        self,
        title: str,
        chapters: list[dict],
        template: Optional[str] = None,
        script_text: Optional[str] = None,
        job_dir: Optional[str] = None,
        steering_context: Optional[dict[str, Any]] = None,
    ) -> str:
        """Generate video description.

        Args:
            title: Video title
            chapters: List of chapters
            template: Optional description template
            script_text: Optional full script text for AI-generated description
            job_dir: Optional job directory to load research sources from

        Returns:
            Formatted description string
        """
        if template:
            return self._enforce_description_hashtag_cap(template)

        # Try to use AI to generate description if script text is available
        if script_text:
            ai_description = self._generate_description_with_ai(title, chapters, script_text, job_dir, steering_context)
            if ai_description:
                return self._enforce_description_hashtag_cap(ai_description)

        # Fallback to default description
        return self._enforce_description_hashtag_cap(self._generate_default_description(title, chapters, job_dir, steering_context))

    def _generate_default_description(self, title: str, chapters: list[dict], job_dir: Optional[str] = None, steering_context: Optional[dict[str, Any]] = None) -> str:
        """Generate a default description when AI fails or isn't available."""
        steering_context = steering_context or {}
        whiskers_handoff = steering_context.get("whiskers_handoff") if isinstance(steering_context.get("whiskers_handoff"), dict) else {}
        ledger_packet = steering_context.get("ledger_packet") if isinstance(steering_context.get("ledger_packet"), dict) else {}
        viewer_problem = str(whiskers_handoff.get("viewer_problem") or title.lower()).strip().rstrip('.')
        stoic_move = str(whiskers_handoff.get("stoic_move") or ledger_packet.get("recommended_angle") or "Use one Stoic move at work this week").strip().rstrip('.')
        hashtags = self._generate_hashtags(title, None, steering_context)
        description = f"""If {viewer_problem.lower()}, this video shows a practical Stoic move you can use at work.

{stoic_move}.

Subscribe to @stoic-modernized for practical Stoic tools you can use at work.

{hashtags}"""
        return self._add_affiliate_links(description, seed_hint=title)

    def _generate_description_with_ai(
        self,
        title: str,
        chapters: list[dict],
        script_text: str,
        job_dir: Optional[str] = None,
        steering_context: Optional[dict[str, Any]] = None,
    ) -> Optional[str]:
        """Generate description using local LLM based on script content.

        Args:
            title: Video title
            chapters: List of chapters with timestamps
            script_text: Full script narration text
            job_dir: Optional job directory to load research sources from

        Returns:
            AI-generated description or None if generation fails
        """
        # Extract the hook (first paragraph or first ~150 chars)
        hook = ""
        if "\n\n" in script_text:
            hook = script_text.split("\n\n")[0][:200]
        elif len(script_text) > 200:
            hook = script_text[:200]
        else:
            hook = script_text

        # Load source URLs from research data if available
        source_links = self._load_source_links(job_dir)

        steering_context = steering_context or {}
        ledger_packet = steering_context.get("ledger_packet") if isinstance(steering_context.get("ledger_packet"), dict) else {}
        whiskers_handoff = steering_context.get("whiskers_handoff") if isinstance(steering_context.get("whiskers_handoff"), dict) else {}
        ledger_strategy = steering_context.get("ledger_strategy") if isinstance(steering_context.get("ledger_strategy"), dict) else {}

        # Stoic Modernized YouTube description prompt
        hashtags = self._generate_hashtags(title, script_text, steering_context)
        prompt = f"""You are a YouTube description writer for the Stoic Modernized channel. Write a very short, hook-driven description (max 50 words total).

Video Title: {title}

Hook from video: {hook}

Steering context:
- packaging angle: {ledger_packet.get("packaging_angle") or ledger_strategy.get("packaging_angle") or ""}
- viewer problem: {whiskers_handoff.get("viewer_problem") or ""}
- stoic move: {whiskers_handoff.get("stoic_move") or ""}
- audience lane: {ledger_packet.get("objective") or ledger_strategy.get("audience_job") or ""}

Write a description that:
1. Opens with 1-2 sentences expanding on the hook while matching the steering context
2. Ends with: "Subscribe to @stoic-modernized for practical Stoic tools you can use at work."
3. Add these hashtags at the end: {hashtags}

Boundary: never promise to send viewers anything. Do not ask viewers to comment, reply, DM, or message to receive a checklist, guide, template, link, PDF, resource, or worksheet.

Keep it extremely tight. No bullet points. No timestamps. No filler. Output only the description text."""

        try:
            import requests

            payload = {
                "model": settings.local_script_model or settings.local_llm_model,
                "messages": [
                    {
                        "role": "system",
                        "content": "You write very short, hook-driven YouTube descriptions. Max 50 words. No bullet points. No timestamps. No filler. Never promise to send viewers anything. Output plain text only.",
                    },
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.7,
                "max_tokens": 200,
                "chat_template_kwargs": {"enable_thinking": False},
            }
            response = requests.post(
                settings.local_llm_base_url,
                json=payload,
                timeout=settings.local_llm_timeout_seconds,
            )
            response.raise_for_status()
            data = response.json()
            content = self._extract_message_content(data)

            if content and content.strip():
                # Clean up any markdown artifacts
                content = re.sub(r"```(?:description)?\s*", "", content, flags=re.IGNORECASE)
                content = re.sub(r"\s*```\s*$", "", content, flags=re.IGNORECASE)
                content = content.strip()
                
                # Add affiliate links before any hashtags
                content = self._add_affiliate_links(content, seed_hint=title)
                
                return content

            return None

        except Exception as e:
            print(f"[yellow]⚠ AI description generation failed: {type(e).__name__}. Using fallback.[/yellow]")
            return None

    def _load_source_links(self, job_dir: Optional[str]) -> list[dict[str, str]]:
        """Load source URLs and names from research JSON in the job directory.

        Returns a list of dicts with 'name' (source type) and 'url'.
        """
        if not job_dir:
            return []
        try:
            research_path = Path(job_dir) / "research" / "research.json"
            if not research_path.exists():
                return []
            data = load_json(research_path)
            sources = data.get("sources", [])
            result = []
            for src in sources[:5]:
                url = src.get("url", "").strip()
                name = (src.get("source") or "web").strip().lower()
                if url:
                    result.append({"name": name, "url": url})
            return result
        except Exception:
            return []

    def _format_sources_section(self, source_links: list[dict[str, str]]) -> str:
        """Format a list of source dicts into a numbered list with URLs only.

        YouTube doesn't support markdown links, so use plain URLs.
        Each line looks like:  1. https://example.com/article
        """
        lines = []
        for i, s in enumerate(source_links, start=1):
            url = s.get("url", "").strip()
            if url:
                lines.append(f"{i}. {url}")
        return "\n".join(lines)

    def _affiliate_link_pool(self) -> list[tuple[str, str]]:
        return [
            ("Meditations by Marcus Aurelius", "https://amzn.to/3Na3Yrw"),
            ("Letters from a Stoic by Seneca", "https://amzn.to/40km3Gj"),
            ("Discourses and Enchiridion", "https://amzn.to/40VhlyR"),
            ("How to Think Like a Roman Emperor: The Stoic Philosophy of Marcus Aurelius", "https://amzn.to/4nnSCxK"),
            ("The Daily Stoic: 366 Meditations on Wisdom, Perseverance, and the Art of Living", "https://amzn.to/4tw8sb8"),
            ("How to Be a Stoic: Using Ancient Philosophy to Live a Modern Life", "https://amzn.to/3PtCaQ1"),
        ]

    def _select_affiliate_links(self, seed_hint: str = "") -> list[tuple[str, str]]:
        pool = self._affiliate_link_pool()
        rng = random.Random(f"{self.channel.value}|{seed_hint}|{datetime.now(UTC).date().isoformat()}")
        return rng.sample(pool, k=min(3, len(pool)))

    def _add_affiliate_links(self, description: str, seed_hint: str = "") -> str:
        """Append a rotating set of affiliate links after the description."""
        selected = self._select_affiliate_links(seed_hint)
        affiliate_lines = "\n".join(f"{title} {url}" for title, url in selected)
        affiliate_links = f"""

Resources:
{affiliate_lines}"""

        return f"{description}{affiliate_links}"

    def _extract_message_content(self, data: dict) -> str:
        """Extract message content from LLM response."""
        choices = data.get("choices") or []
        if not choices:
            return ""
        message = choices[0].get("message") or {}
        content = message.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            text_parts = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    text_parts.append(str(item.get("text") or ""))
            return "\n".join(part for part in text_parts if part)
        return ""
