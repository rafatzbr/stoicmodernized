"""Fetch fresh Facebook Page/Reels metrics artifacts and regenerate Milo strategy.

Usage:
    python -m src.refresh_facebook_metrics
    python -m src.refresh_facebook_metrics --lookback-days 28
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import requests

from src.config import settings
from src.ledger_strategy import LedgerStrategyManager
from src.utils import save_json

PAGE_INSIGHT_METRICS = (
    "page_video_views",
    "page_post_engagements",
    "page_impressions_unique",
)
VIDEO_INSIGHT_METRICS = (
    "total_video_views",
    "total_video_10s_views",
    "total_video_complete_views",
    "total_video_avg_time_watched",
    "total_video_reactions_by_type_total",
)


@dataclass
class ArtifactPaths:
    metrics_md: Path
    analytics_md: Path
    snapshot_json: Path


def _graph_base() -> str:
    return f"https://graph.facebook.com/{settings.meta_graph_api_version}"


def _sanitize_meta_text(text: str) -> str:
    text = re.sub(r"access_token=[^&\s\"]+", "access_token=[REDACTED]", text)
    for secret in (settings.meta_page_access_token, settings.meta_app_secret):
        if secret:
            text = text.replace(secret, "[REDACTED]")
    return text


def _get_json(url: str, *, params: dict[str, Any], timeout: int = 30) -> dict[str, Any]:
    try:
        response = requests.get(url, params=params, timeout=timeout)
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:  # pragma: no cover - exact requests exception type varies
        raise RuntimeError(_sanitize_meta_text(str(exc))) from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"Unexpected Meta response type: {type(payload).__name__}")
    return payload


def _resolve_page_access_token(graph: str, access_token: str) -> str:
    payload = _get_json(
        f"{graph}/{settings.facebook_page_id}",
        params={"fields": "access_token", "access_token": access_token},
    )
    page_token = payload.get("access_token")
    if not page_token:
        raise RuntimeError("Could not resolve Facebook Page access token from configured META_PAGE_ACCESS_TOKEN")
    return str(page_token)


def _access_token(graph: str) -> str:
    if not settings.meta_page_access_token:
        raise RuntimeError("Missing META_PAGE_ACCESS_TOKEN for Facebook metrics refresh")
    if not settings.facebook_page_id:
        raise RuntimeError("Missing FACEBOOK_PAGE_ID for Facebook metrics refresh")
    return _resolve_page_access_token(graph, settings.meta_page_access_token)


def _sum_numeric_insight_values(insights: dict[str, Any]) -> dict[str, Any]:
    totals: dict[str, Any] = {}
    for item in insights.get("data", []) or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "")
        values = item.get("values") or []
        if not name or not isinstance(values, list):
            continue
        total: float | int | None = 0
        raw_values: list[Any] = []
        for value_item in values:
            if not isinstance(value_item, dict):
                continue
            value = value_item.get("value")
            raw_values.append(value)
            if isinstance(value, (int, float)):
                total = (total or 0) + value
            elif isinstance(value, dict):
                subtotal = sum(v for v in value.values() if isinstance(v, (int, float)))
                total = (total or 0) + subtotal
            else:
                total = None
        totals[name] = total if total is not None else raw_values[-1] if raw_values else None
    return totals


def _fetch_page_snapshot(graph: str, page_token: str) -> dict[str, Any]:
    return _get_json(
        f"{graph}/{settings.facebook_page_id}",
        params={
            "fields": "id,name,link,fan_count,followers_count",
            "access_token": page_token,
        },
    )


def _fetch_page_insights(graph: str, page_token: str, start_date: date, end_date: date) -> dict[str, Any]:
    try:
        payload = _get_json(
            f"{graph}/{settings.facebook_page_id}/insights",
            params={
                "metric": ",".join(PAGE_INSIGHT_METRICS),
                "period": "day",
                "since": start_date.isoformat(),
                "until": end_date.isoformat(),
                "access_token": page_token,
            },
        )
        return {"raw": payload, "totals": _sum_numeric_insight_values(payload), "error": None}
    except RuntimeError as exc:
        return {"raw": {}, "totals": {}, "error": str(exc)}


def _fetch_page_videos(graph: str, page_token: str, limit: int) -> list[dict[str, Any]]:
    payload = _get_json(
        f"{graph}/{settings.facebook_page_id}/videos",
        params={
            "fields": "id,title,description,created_time,permalink_url,length",
            "limit": min(max(limit, 1), 100),
            "access_token": page_token,
        },
    )
    return [item for item in payload.get("data", []) or [] if isinstance(item, dict)]


def _fetch_video_insights(graph: str, page_token: str, video_id: str) -> dict[str, Any]:
    try:
        payload = _get_json(
            f"{graph}/{video_id}/video_insights",
            params={"metric": ",".join(VIDEO_INSIGHT_METRICS), "access_token": page_token},
        )
        return {"raw": payload, "totals": _sum_numeric_insight_values(payload), "error": None}
    except RuntimeError as exc:
        return {"raw": {}, "totals": {}, "error": str(exc)}


def _title_for_video(video: dict[str, Any]) -> str:
    title = str(video.get("title") or "").strip()
    if title:
        return title
    description = str(video.get("description") or "").strip().splitlines()[0:1]
    if description:
        text = description[0].strip()
        return text[:90] + ("…" if len(text) > 90 else "")
    return str(video.get("id") or "Unknown Facebook video")


def _fetch_analytics(graph: str, page_token: str, start_date: date, end_date: date, video_limit: int) -> dict[str, Any]:
    page_snapshot = _fetch_page_snapshot(graph, page_token)
    page_insights = _fetch_page_insights(graph, page_token, start_date, end_date)
    videos = _fetch_page_videos(graph, page_token, video_limit)
    enriched: list[dict[str, Any]] = []
    for video in videos:
        video_id = str(video.get("id") or "")
        if not video_id:
            continue
        insights = _fetch_video_insights(graph, page_token, video_id)
        enriched.append({**video, "title_for_ledger": _title_for_video(video), "insights": insights})
    enriched.sort(key=lambda item: int((item.get("insights") or {}).get("totals", {}).get("total_video_views") or 0), reverse=True)
    return {
        "window": {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "lookback_days": (end_date - start_date).days + 1,
        },
        "page_snapshot": page_snapshot,
        "page_insights": page_insights,
        "top_videos": enriched[:10],
    }


def _artifact_paths(workspace_root: Path, stamp: str) -> ArtifactPaths:
    artifacts_dir = workspace_root / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    return ArtifactPaths(
        metrics_md=artifacts_dir / f"stoic-modernized-facebook-metrics-{stamp}.md",
        analytics_md=artifacts_dir / f"stoic-modernized-facebook-analytics-{stamp}.md",
        snapshot_json=artifacts_dir / f"stoic-modernized-facebook-analytics-snapshot-{stamp}.json",
    )


def _fmt_int(value: Any) -> str:
    try:
        return f"{int(float(value)):,}"
    except (TypeError, ValueError):
        return str(value)


def _write_metrics_md(path: Path, analytics_data: dict[str, Any], generated_at: str) -> None:
    page = analytics_data.get("page_snapshot", {})
    page_totals = analytics_data.get("page_insights", {}).get("totals", {})
    lines = [
        f"# Stoic Modernized Facebook Metrics — {generated_at[:10]}",
        "",
        "## Page snapshot",
        f"- Page: {page.get('name', 'Unknown')}",
        f"- Page ID: {page.get('id', settings.facebook_page_id or '')}",
        f"- Followers: {_fmt_int(page.get('followers_count', 0))}",
        f"- Fans: {_fmt_int(page.get('fan_count', 0))}",
        f"- Link: {page.get('link', '')}",
        "",
        f"## Analytics window ({analytics_data['window']['start_date']} → {analytics_data['window']['end_date']})",
        f"- Page video views: {_fmt_int(page_totals.get('page_video_views', 0))}",
        f"- Page post engagements: {_fmt_int(page_totals.get('page_post_engagements', 0))}",
        f"- Page unique impressions/reach: {_fmt_int(page_totals.get('page_impressions_unique', 0))}",
        "",
        "## Top Facebook videos by lifetime views",
    ]
    for idx, video in enumerate(analytics_data.get("top_videos", []), start=1):
        insights = video.get("insights") or {}
        totals = insights.get("totals", {})
        unavailable = "unavailable" if insights.get("error") else None
        lines.extend(
            [
                f"{idx}. {video.get('title_for_ledger', video.get('id', 'Unknown Facebook video'))}",
                f"   - Facebook video ID: {video.get('id', '')}",
                f"   - Created: {video.get('created_time', '')}",
                f"   - Views: {unavailable or _fmt_int(totals.get('total_video_views', 0))}",
                f"   - 10-second views: {unavailable or _fmt_int(totals.get('total_video_10s_views', 0))}",
                f"   - Complete views: {unavailable or _fmt_int(totals.get('total_video_complete_views', 0))}",
                f"   - Average time watched: {unavailable or _fmt_int(totals.get('total_video_avg_time_watched', 0))}",
                f"   - URL: {video.get('permalink_url', '')}",
            ]
        )
    page_error = analytics_data.get("page_insights", {}).get("error")
    video_errors = [str((video.get("insights") or {}).get("error")) for video in analytics_data.get("top_videos", []) if (video.get("insights") or {}).get("error")]
    if page_error or video_errors:
        lines.extend(["", "## Refresh warnings"])
        if page_error:
            lines.append(f"- Page insights: {page_error}")
        for error in video_errors[:5]:
            lines.append(f"- Video insights: {error}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_analytics_md(path: Path, analytics_data: dict[str, Any], generated_at: str) -> None:
    page_totals = analytics_data.get("page_insights", {}).get("totals", {})
    lines = [
        f"# Stoic Modernized Facebook Analytics — {generated_at[:10]}",
        "",
        f"## Window\n- {analytics_data['window']['start_date']} → {analytics_data['window']['end_date']}",
        "",
        "## Page totals",
    ]
    for key, value in page_totals.items():
        lines.append(f"- {key}: {_fmt_int(value)}")
    lines.extend(["", "## Notes for Milo", "- Join with YouTube and manual TikTok artifacts before the next topic batch or script council run."])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run(
    lookback_days: int = 28,
    workspace_root: Path | None = None,
    project_root: Path | None = None,
    video_limit: int = 25,
) -> dict[str, Any]:
    workspace_root = workspace_root or (Path.home() / ".openclaw" / "workspace")
    project_root = project_root or Path(__file__).resolve().parent.parent
    generated_at = datetime.now(UTC).isoformat()
    end_date = datetime.now(UTC).date()
    start_date = end_date - timedelta(days=max(lookback_days - 1, 0))

    graph = _graph_base()
    page_token = _access_token(graph)
    analytics_data = _fetch_analytics(graph, page_token, start_date, end_date, video_limit)

    stamp = generated_at[:10]
    paths = _artifact_paths(workspace_root, stamp)
    payload = {"generated_at": generated_at, "analytics": analytics_data}
    save_json(payload, paths.snapshot_json)
    _write_metrics_md(paths.metrics_md, analytics_data, generated_at)
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
    parser = argparse.ArgumentParser(description="Refresh Stoic Modernized Facebook metrics artifacts and Milo strategy.")
    parser.add_argument("--lookback-days", type=int, default=28, help="Number of trailing days to query from Meta Page insights.")
    parser.add_argument("--video-limit", type=int, default=25, help="Number of recent Page videos/Reels to inspect.")
    args = parser.parse_args()
    result = run(lookback_days=args.lookback_days, video_limit=args.video_limit)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
