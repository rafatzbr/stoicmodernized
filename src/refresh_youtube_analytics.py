"""Fetch fresh YouTube analytics artifacts and regenerate Ledger strategy.

Usage:
    python -m src.refresh_youtube_analytics
    python -m src.refresh_youtube_analytics --lookback-days 28
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from src.ledger_strategy import LedgerStrategyManager
from src.utils import save_json

REQUIRED_SCOPES = {
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
}


@dataclass
class ArtifactPaths:
    metrics_md: Path
    analytics_md: Path
    snapshot_json: Path


def _token_path() -> Path:
    return Path.home() / ".stoic-modernized" / "stoic-modernized" / "oauth2_token.json"


def _load_credentials() -> Credentials:
    token_path = _token_path()
    if not token_path.exists():
        raise FileNotFoundError(
            f"OAuth token not found at {token_path}. Run: python -m src.auth_oauth --channel stoic-modernized"
        )

    token_payload = json.loads(token_path.read_text(encoding="utf-8"))
    token_scopes = set(token_payload.get("scopes") or [])
    missing_scopes = sorted(REQUIRED_SCOPES - token_scopes)
    if missing_scopes:
        raise RuntimeError(
            "OAuth token is missing required scopes for analytics refresh: "
            + ", ".join(missing_scopes)
            + ". Run: python -m src.auth_oauth --channel stoic-modernized"
        )

    creds = Credentials.from_authorized_user_file(str(token_path))
    if not creds.valid and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        token_path.write_text(creds.to_json(), encoding="utf-8")
    if not creds.valid:
        raise RuntimeError(
            "OAuth token is invalid. Run: python -m src.auth_oauth --channel stoic-modernized"
        )
    return creds


def _build_services() -> tuple[Any, Any]:
    creds = _load_credentials()
    youtube = build("youtube", "v3", credentials=creds)
    analytics = build("youtubeAnalytics", "v2", credentials=creds)
    return youtube, analytics


def _query_report(service: Any, **kwargs: Any) -> dict[str, Any]:
    return service.reports().query(**kwargs).execute()


def _report_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    headers = [item.get("name") for item in payload.get("columnHeaders", [])]
    rows: list[dict[str, Any]] = []
    for raw in payload.get("rows", []) or []:
        rows.append({headers[i]: raw[i] for i in range(min(len(headers), len(raw)))})
    return rows


def _fetch_channel_snapshot(youtube: Any) -> dict[str, Any]:
    response = youtube.channels().list(part="snippet,statistics", mine=True).execute()
    items = response.get("items", [])
    if not items:
        raise RuntimeError("No YouTube channel found for the authenticated token.")
    item = items[0]
    return {
        "channel_id": item["id"],
        "channel_title": item["snippet"]["title"],
        "published_at": item["snippet"].get("publishedAt"),
        "subscriber_count": int(item.get("statistics", {}).get("subscriberCount", 0)),
        "view_count": int(item.get("statistics", {}).get("viewCount", 0)),
        "video_count": int(item.get("statistics", {}).get("videoCount", 0)),
    }


def _fetch_video_titles(youtube: Any, video_ids: list[str]) -> dict[str, str]:
    if not video_ids:
        return {}
    response = youtube.videos().list(part="snippet", id=",".join(video_ids[:50])).execute()
    return {item["id"]: item.get("snippet", {}).get("title", item["id"]) for item in response.get("items", [])}


def _fetch_analytics(youtube: Any, analytics: Any, start_date: date, end_date: date) -> dict[str, Any]:
    ids = "channel==MINE"
    start = start_date.isoformat()
    end = end_date.isoformat()

    summary = _report_rows(
        _query_report(
            analytics,
            ids=ids,
            startDate=start,
            endDate=end,
            metrics="views,estimatedMinutesWatched,averageViewDuration,likes,comments,shares,subscribersGained,subscribersLost",
        )
    )
    top_videos = _report_rows(
        _query_report(
            analytics,
            ids=ids,
            startDate=start,
            endDate=end,
            dimensions="video",
            metrics="views,estimatedMinutesWatched,averageViewDuration,likes,comments,shares,subscribersGained",
            sort="-views",
            maxResults=10,
        )
    )
    traffic_sources = _report_rows(
        _query_report(
            analytics,
            ids=ids,
            startDate=start,
            endDate=end,
            dimensions="insightTrafficSourceType",
            metrics="views,estimatedMinutesWatched",
            sort="-views",
            maxResults=10,
        )
    )
    subscribed_status = _report_rows(
        _query_report(
            analytics,
            ids=ids,
            startDate=start,
            endDate=end,
            dimensions="subscribedStatus",
            metrics="views,estimatedMinutesWatched",
        )
    )
    device_type = _report_rows(
        _query_report(
            analytics,
            ids=ids,
            startDate=start,
            endDate=end,
            dimensions="deviceType",
            metrics="views",
            sort="-views",
            maxResults=10,
        )
    )

    title_map = _fetch_video_titles(youtube, [str(row.get("video")) for row in top_videos if row.get("video")])
    for row in top_videos:
        video_id = str(row.get("video") or "")
        row["title"] = title_map.get(video_id, video_id)

    return {
        "window": {
            "start_date": start,
            "end_date": end,
            "lookback_days": (end_date - start_date).days + 1,
        },
        "summary": summary[0] if summary else {},
        "top_videos": top_videos,
        "traffic_sources": traffic_sources,
        "subscribed_status": subscribed_status,
        "device_type": device_type,
    }


def _artifact_paths(workspace_root: Path, stamp: str) -> ArtifactPaths:
    artifacts_dir = workspace_root / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    return ArtifactPaths(
        metrics_md=artifacts_dir / f"stoic-modernized-youtube-metrics-{stamp}.md",
        analytics_md=artifacts_dir / f"stoic-modernized-youtube-analytics-{stamp}.md",
        snapshot_json=artifacts_dir / f"stoic-modernized-youtube-analytics-snapshot-{stamp}.json",
    )


def _fmt_int(value: Any) -> str:
    try:
        return f"{int(float(value)):,}"
    except (TypeError, ValueError):
        return str(value)


def _fmt_float(value: Any, digits: int = 1) -> str:
    try:
        return f"{float(value):.{digits}f}"
    except (TypeError, ValueError):
        return str(value)


def _write_metrics_md(path: Path, snapshot: dict[str, Any], analytics_data: dict[str, Any], generated_at: str) -> None:
    summary = analytics_data.get("summary", {})
    lines = [
        f"# Stoic Modernized YouTube Metrics — {generated_at[:10]}",
        "",
        "## Channel snapshot",
        f"- Channel: {snapshot['channel_title']}",
        f"- Channel ID: {snapshot['channel_id']}",
        f"- Subscribers: {_fmt_int(snapshot['subscriber_count'])}",
        f"- Lifetime views: {_fmt_int(snapshot['view_count'])}",
        f"- Lifetime videos: {_fmt_int(snapshot['video_count'])}",
        "",
        f"## Analytics window ({analytics_data['window']['start_date']} → {analytics_data['window']['end_date']})",
        f"- Views: {_fmt_int(summary.get('views', 0))}",
        f"- Estimated minutes watched: {_fmt_int(summary.get('estimatedMinutesWatched', 0))}",
        f"- Average view duration (seconds): {_fmt_float(summary.get('averageViewDuration', 0), 1)}",
        f"- Likes: {_fmt_int(summary.get('likes', 0))}",
        f"- Comments: {_fmt_int(summary.get('comments', 0))}",
        f"- Shares: {_fmt_int(summary.get('shares', 0))}",
        f"- Subscribers gained: {_fmt_int(summary.get('subscribersGained', 0))}",
        f"- Subscribers lost: {_fmt_int(summary.get('subscribersLost', 0))}",
        "",
        "## Top videos in window",
    ]
    for idx, row in enumerate(analytics_data.get("top_videos", []), start=1):
        lines.extend(
            [
                f"{idx}. {row.get('title', row.get('video', 'Unknown video'))}",
                f"   - Video ID: {row.get('video', '')}",
                f"   - Views: {_fmt_int(row.get('views', 0))}",
                f"   - Minutes watched: {_fmt_int(row.get('estimatedMinutesWatched', 0))}",
                f"   - Avg view duration (seconds): {_fmt_float(row.get('averageViewDuration', 0), 1)}",
                f"   - Likes/Comments/Shares: {_fmt_int(row.get('likes', 0))}/{_fmt_int(row.get('comments', 0))}/{_fmt_int(row.get('shares', 0))}",
                f"   - Subscribers gained: {_fmt_int(row.get('subscribersGained', 0))}",
            ]
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_analytics_md(path: Path, analytics_data: dict[str, Any], generated_at: str) -> None:
    lines = [
        f"# Stoic Modernized YouTube Analytics — {generated_at[:10]}",
        "",
        f"## Window\n- {analytics_data['window']['start_date']} → {analytics_data['window']['end_date']}",
        "",
        "## Traffic sources",
    ]
    for row in analytics_data.get("traffic_sources", []):
        lines.append(
            f"- {row.get('insightTrafficSourceType', 'unknown')}: {_fmt_int(row.get('views', 0))} views, {_fmt_int(row.get('estimatedMinutesWatched', 0))} minutes watched"
        )
    lines.extend(["", "## Subscriber status"])
    for row in analytics_data.get("subscribed_status", []):
        lines.append(
            f"- {row.get('subscribedStatus', 'unknown')}: {_fmt_int(row.get('views', 0))} views, {_fmt_int(row.get('estimatedMinutesWatched', 0))} minutes watched"
        )
    lines.extend(["", "## Device types"])
    for row in analytics_data.get("device_type", []):
        lines.append(f"- {row.get('deviceType', 'unknown')}: {_fmt_int(row.get('views', 0))} views")
    lines.extend(["", "## Notes for Ledger", "- Refresh global strategy from these artifacts before the next topic batch or script council run."])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run(lookback_days: int = 28, workspace_root: Path | None = None, project_root: Path | None = None) -> dict[str, Any]:
    workspace_root = workspace_root or (Path.home() / ".openclaw" / "workspace")
    project_root = project_root or Path(__file__).resolve().parent.parent
    generated_at = datetime.now(UTC).isoformat()
    end_date = datetime.now(UTC).date()
    start_date = end_date - timedelta(days=max(lookback_days - 1, 0))

    youtube, analytics = _build_services()
    snapshot = _fetch_channel_snapshot(youtube)
    analytics_data = _fetch_analytics(youtube, analytics, start_date, end_date)

    stamp = generated_at[:10]
    paths = _artifact_paths(workspace_root, stamp)
    payload = {
        "generated_at": generated_at,
        "channel_snapshot": snapshot,
        "analytics": analytics_data,
    }
    save_json(payload, paths.snapshot_json)
    _write_metrics_md(paths.metrics_md, snapshot, analytics_data, generated_at)
    _write_analytics_md(paths.analytics_md, analytics_data, generated_at)

    manager = LedgerStrategyManager(project_root=project_root, workspace_root=workspace_root)
    strategy = manager.generate_global_strategy()
    topic_plan = manager.generate_topic_plan()

    return {
        "generated_at": generated_at,
        "metrics_md": str(paths.metrics_md),
        "analytics_md": str(paths.analytics_md),
        "snapshot_json": str(paths.snapshot_json),
        "strategy_generated_at": strategy.get("generated_at"),
        "topic_plan_generated_at": topic_plan.get("generated_at"),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Refresh Stoic Modernized YouTube analytics artifacts and Ledger strategy.")
    parser.add_argument("--lookback-days", type=int, default=28, help="Number of trailing days to query from YouTube Analytics.")
    args = parser.parse_args()
    result = run(lookback_days=args.lookback_days)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
