"""Background music download stage using Pixabay Music scraping."""

from __future__ import annotations

import json
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Optional

from src.config import settings
from src.utils import save_json


class PixabayMusicDownloader:
    """Search and download royalty-free background music from Pixabay."""

    _USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    )

    _BROWSER_HEADERS = {
        "Accept": (
            "text/html,application/xhtml+xml,application/xml;"
            "q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8"
        ),
        "Accept-Language": "en-US,en;q=0.9",
        "Sec-Ch-Ua": '"Chromium";v="131", "Not_A Brand";v="24"',
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": '"Windows"',
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Upgrade-Insecure-Requests": "1",
    }

    def _build_opener(self) -> urllib.request.OpenerDirector:
        import http.cookiejar

        cookie_jar = http.cookiejar.CookieJar()
        return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookie_jar))

    def search(self, query: str) -> list[dict[str, Any]]:
        slug = re.sub(r"\s+", "-", query.strip().lower())
        slug = urllib.parse.quote(slug, safe="-")
        search_url = f"https://pixabay.com/music/search/{slug}/"

        opener = self._build_opener()
        request = urllib.request.Request(search_url)
        request.add_header("User-Agent", self._USER_AGENT)
        for key, value in self._BROWSER_HEADERS.items():
            request.add_header(key, value)

        with opener.open(request, timeout=30) as response:
            html = response.read().decode("utf-8", errors="replace")

        tracks = self._parse_bootstrap(html=html, referer=search_url, opener=opener)
        if tracks:
            return tracks

        return self._parse_tracks_html(html)

    def _parse_bootstrap(
        self,
        *,
        html: str,
        referer: str,
        opener: urllib.request.OpenerDirector,
    ) -> list[dict[str, Any]]:
        match = re.search(
            r'window\.__BOOTSTRAP_URL__\s*=\s*["\']([^"\']+)["\']',
            html,
        )
        if not match:
            return []

        bootstrap_path = match.group(1)
        if not bootstrap_path:
            return []

        bootstrap_url = f"https://pixabay.com{bootstrap_path}"
        request = urllib.request.Request(bootstrap_url)
        request.add_header("User-Agent", self._USER_AGENT)
        request.add_header("Accept", "application/json, text/plain, */*")
        request.add_header("Referer", referer)
        request.add_header("Sec-Fetch-Dest", "empty")
        request.add_header("Sec-Fetch-Mode", "cors")
        request.add_header("Sec-Fetch-Site", "same-origin")

        try:
            with opener.open(request, timeout=15) as response:
                data = json.loads(response.read().decode("utf-8"))
        except Exception:
            return []

        results = data.get("page", {}).get("results", [])
        tracks: list[dict[str, Any]] = []
        for item in results:
            sources = item.get("sources", {}) or {}
            audio_url = sources.get("src")
            if not audio_url:
                continue

            user = item.get("user", {}) or {}
            tracks.append(
                {
                    "title": item.get("name") or sources.get("filename", "Unknown"),
                    "audio_url": audio_url,
                    "duration": item.get("duration"),
                    "artist": user.get("username", "Unknown"),
                    "rating": item.get("rating"),
                    "download_count": item.get("downloadCount"),
                    "pixabay_id": item.get("id"),
                }
            )

        return tracks

    def _parse_tracks_html(self, html: str) -> list[dict[str, Any]]:
        tracks: list[dict[str, Any]] = []
        mp3_urls = re.findall(
            r'(https?://cdn\.pixabay\.com/audio/[^\s"\'<>]+\.mp3[^\s"\'<>]*)',
            html,
        )
        seen: set[str] = set()
        for url in mp3_urls:
            if url in seen:
                continue
            seen.add(url)
            tracks.append(
                {
                    "title": "Unknown",
                    "audio_url": url,
                    "duration": None,
                    "artist": "Unknown",
                }
            )
        return tracks

    def choose_track(
        self,
        tracks: list[dict[str, Any]],
        *,
        min_duration: int,
        max_duration: int,
        target_duration: Optional[float],
    ) -> dict[str, Any]:
        if not tracks:
            raise RuntimeError("No Pixabay tracks were found")

        filtered = [
            track
            for track in tracks
            if track.get("duration") is not None and min_duration <= track["duration"] <= max_duration
        ]
        candidates = filtered or tracks

        def score(track: dict[str, Any]) -> tuple[float, float, float]:
            duration = track.get("duration")
            distance_anchor = target_duration or duration or float(min_duration)
            distance = abs((duration or distance_anchor) - distance_anchor)
            rating = float(track.get("rating") or 0)
            downloads = float(track.get("download_count") or 0)
            return (distance, -rating, -downloads)

        return sorted(candidates, key=score)[0]

    def download(self, track: dict[str, Any], output_path: Path) -> Path:
        audio_url = track.get("audio_url")
        if not audio_url:
            raise RuntimeError("Selected Pixabay track has no audio URL")

        if audio_url.startswith("//"):
            audio_url = "https:" + audio_url
        elif audio_url.startswith("/"):
            audio_url = "https://pixabay.com" + audio_url

        output_path.parent.mkdir(parents=True, exist_ok=True)
        request = urllib.request.Request(
            audio_url,
            headers={
                "User-Agent": self._USER_AGENT,
                "Referer": "https://pixabay.com/music/",
            },
        )
        with urllib.request.urlopen(request, timeout=60) as response:
            output_path.write_bytes(response.read())
        return output_path


class BackgroundMusicStage:
    """Download royalty-free background music for a job."""

    def __init__(self, job_id: str):
        self.job_id = job_id
        self.job_dir = settings.jobs_dir / job_id
        self.audio_dir = self.job_dir / "audio"
        self.output_path = self.audio_dir / "background_music.mp3"
        self.metadata_path = self.audio_dir / "background_music.json"
        self.downloader = PixabayMusicDownloader()

    def build_query(self, topic: str, query: Optional[str] = None) -> str:
        if query:
            return query.strip()

        base_query = settings.background_music_query.strip()
        topic_keywords = " ".join(re.findall(r"[A-Za-z]+", topic)[:4]).strip().lower()
        if topic_keywords and topic_keywords not in base_query.lower():
            return f"{base_query} {topic_keywords}".strip()
        return base_query or "calm ambient instrumental background music"

    def _get_audio_duration(self, audio_path: Optional[str]) -> Optional[float]:
        if not audio_path:
            return None

        import subprocess

        try:
            probe = subprocess.run(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-show_entries",
                    "format=duration",
                    "-of",
                    "default=noprint_wrappers=1:nokey=1",
                    audio_path,
                ],
                capture_output=True,
                text=True,
                check=True,
            )
            return float(probe.stdout.strip())
        except Exception:
            return None

    async def run(self, topic: str, audio_path: Optional[str] = None, query: Optional[str] = None) -> Path:
        self.audio_dir.mkdir(parents=True, exist_ok=True)
        target_duration = self._get_audio_duration(audio_path)
        min_duration = settings.background_music_min_duration
        max_duration = settings.background_music_max_duration

        if target_duration:
            min_duration = max(min_duration, int(max(15, target_duration * 0.6)))
            max_duration = min(max_duration, int(max(min_duration, target_duration * 1.75)))

        search_query = self.build_query(topic, query=query)
        started_at = time.time()
        tracks = self.downloader.search(search_query)
        track = self.downloader.choose_track(
            tracks,
            min_duration=min_duration,
            max_duration=max_duration,
            target_duration=target_duration,
        )
        output_path = self.downloader.download(track, self.output_path)

        save_json(
            {
                "provider": "pixabay",
                "query": search_query,
                "downloaded_at": time.time(),
                "target_duration": target_duration,
                "min_duration": min_duration,
                "max_duration": max_duration,
                "track": track,
                "output": str(output_path),
                "license": "Pixabay Content License",
                "elapsed_seconds": round(time.time() - started_at, 2),
            },
            self.metadata_path,
        )
        return output_path
