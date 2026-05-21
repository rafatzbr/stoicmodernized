"""Persistent registry of previously covered news stories."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any
import re

from src.config import Channel, settings
from src.utils import load_json, save_json


class NewsRegistry:
    """Stores news stories that have already been covered in videos."""

    GENERIC_NEWS_WORDS = {
        "a",
        "an",
        "and",
        "announces",
        "announced",
        "artificial",
        "at",
        "big",
        "billion",
        "builds",
        "company",
        "companies",
        "deal",
        "expands",
        "for",
        "from",
        "gets",
        "in",
        "into",
        "launch",
        "launches",
        "latest",
        "made",
        "makes",
        "model",
        "new",
        "news",
        "of",
        "on",
        "over",
        "raises",
        "release",
        "reports",
        "rollout",
        "says",
        "the",
        "to",
        "up",
        "update",
        "with",
    }

    IMPORTANT_AI_TERMS = {
        "openai",
        "anthropic",
        "google",
        "gemini",
        "microsoft",
        "copilot",
        "nvidia",
        "meta",
        "claude",
        "gpt",
        "chatgpt",
        "llama",
        "xai",
        "grok",
        "amazon",
        "aws",
        "tesla",
        "mistral",
        "perplexity",
        "deepmind",
        "runway",
        "midjourney",
        "stability",
    }

    def __init__(self, path: Path | None = None):
        self.path = path or (settings.output_dir / "covered_news.json")

    def load(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        payload = load_json(self.path)
        if isinstance(payload, list):
            return payload
        return []

    def save(self, entries: list[dict[str, Any]]) -> Path:
        return save_json(entries, self.path)

    def get_entries(self, channel: Channel) -> list[dict[str, Any]]:
        return [entry for entry in self.load() if entry.get("channel") == channel.value]

    def is_likely_duplicate(self, channel: Channel, *, title: str, url: str, note: str = "") -> bool:
        normalized_title = self._normalize_title(title)
        normalized_url = self._normalize_url(url)
        candidate_tokens = self._story_tokens(title, note)
        candidate_signature = self._story_signature(title, note)

        for entry in self.get_entries(channel):
            existing_url = self._normalize_url(str(entry.get("url") or ""))
            if normalized_url and existing_url == normalized_url:
                return True

            existing_title = str(entry.get("title") or "")
            existing_note = str(entry.get("note") or "")
            normalized_existing_title = self._normalize_title(existing_title)
            if normalized_title and normalized_existing_title and normalized_title == normalized_existing_title:
                return True

            existing_signature = self._story_signature(existing_title, existing_note)
            if candidate_signature and existing_signature and candidate_signature == existing_signature:
                return True

            existing_tokens = self._story_tokens(existing_title, existing_note)
            if self._is_token_duplicate(candidate_tokens, existing_tokens):
                return True

        return False

    def add_entries(self, channel: Channel, entries: list[dict[str, Any]]) -> int:
        existing = self.load()
        added = 0
        for entry in entries:
            title = str(entry.get("title") or "").strip()
            url = str(entry.get("url") or "").strip()
            note = str(entry.get("note") or "").strip()
            if not title or not url:
                continue
            if self.is_likely_duplicate(channel, title=title, url=url, note=note):
                continue
            existing.append(entry)
            added += 1
        if added:
            self.save(existing)
        return added

    def build_entries_for_job(
        self,
        *,
        job_id: str,
        channel: Channel,
        topic: str,
        video_title: str,
        sources: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        created_at = datetime.now(UTC).isoformat()
        entries: list[dict[str, Any]] = []
        for source in sources:
            title = str(source.get("title") or "").strip()
            url = str(source.get("url") or "").strip()
            note = str(source.get("note") or "").strip()
            if not title or not url:
                continue
            entries.append(
                {
                    "job_id": job_id,
                    "channel": channel.value,
                    "topic": topic,
                    "video_title": video_title,
                    "title": title,
                    "url": url,
                    "note": note,
                    "source": str(source.get("source") or "").strip(),
                    "story_signature": self._story_signature(title, note),
                    "story_tokens": sorted(self._story_tokens(title, note)),
                    "saved_at": created_at,
                }
            )
        return entries

    def _normalize_title(self, title: str) -> str:
        lowered = title.lower().strip()
        lowered = re.sub(r"\$\s?(\d+)", r"\1", lowered)
        lowered = re.sub(r"[^a-z0-9\s]", " ", lowered)
        lowered = re.sub(r"\s+", " ", lowered).strip()
        return lowered

    def _normalize_url(self, url: str) -> str:
        normalized = url.strip().lower()
        normalized = normalized.split("#", 1)[0]
        normalized = normalized.split("?", 1)[0]
        if normalized.endswith("/"):
            normalized = normalized[:-1]
        return normalized

    def _story_signature(self, title: str, note: str) -> str:
        tokens = sorted(self._story_tokens(title, note))
        if not tokens:
            return ""
        return "|".join(tokens[:8])

    def _story_tokens(self, title: str, note: str) -> set[str]:
        title_tokens = set(self._extract_tokens(title))
        note_tokens = set(self._extract_tokens(note))
        important = {token for token in (title_tokens | note_tokens) if token in self.IMPORTANT_AI_TERMS}
        numeric = {token for token in title_tokens if any(ch.isdigit() for ch in token)}
        strong_title_tokens = {token for token in title_tokens if len(token) >= 4 and token not in self.GENERIC_NEWS_WORDS}
        supporting_note_tokens = {token for token in note_tokens if len(token) >= 5 and token not in self.GENERIC_NEWS_WORDS}
        combined = important | numeric | strong_title_tokens | set(sorted(supporting_note_tokens)[:6])
        return {token for token in combined if token}

    def _extract_tokens(self, text: str) -> list[str]:
        normalized = self._normalize_title(text)
        return [token for token in normalized.split() if token and token not in self.GENERIC_NEWS_WORDS]

    def _is_token_duplicate(self, candidate_tokens: set[str], existing_tokens: set[str]) -> bool:
        if not candidate_tokens or not existing_tokens:
            return False

        overlap = candidate_tokens & existing_tokens
        if len(overlap) < 2:
            return False

        candidate_ai_terms = candidate_tokens & self.IMPORTANT_AI_TERMS
        existing_ai_terms = existing_tokens & self.IMPORTANT_AI_TERMS
        if candidate_ai_terms and existing_ai_terms and not (candidate_ai_terms & existing_ai_terms):
            return False

        smallest_size = min(len(candidate_tokens), len(existing_tokens))
        overlap_ratio = len(overlap) / max(1, smallest_size)

        if overlap_ratio >= 0.8:
            return True
        if len(overlap) >= 4:
            return True
        if len(overlap) >= 3 and bool(candidate_ai_terms & existing_ai_terms):
            return True
        if any(token.isdigit() for token in overlap) and len(overlap) >= 3:
            return True
        return False


news_registry = NewsRegistry()
