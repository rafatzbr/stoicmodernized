from pathlib import Path

from src.refresh_youtube_analytics import run


def test_run_writes_artifacts_and_refreshes_ledger(monkeypatch, tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    project = tmp_path / "project"
    (workspace / "artifacts").mkdir(parents=True, exist_ok=True)
    (project / "state").mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr("src.refresh_youtube_analytics._build_services", lambda: (object(), object()))
    monkeypatch.setattr(
        "src.refresh_youtube_analytics._fetch_channel_snapshot",
        lambda _youtube: {
            "channel_id": "abc123",
            "channel_title": "Stoic Modernized",
            "published_at": "2026-01-01T00:00:00Z",
            "subscriber_count": 7,
            "view_count": 1200,
            "video_count": 25,
        },
    )
    monkeypatch.setattr(
        "src.refresh_youtube_analytics._fetch_analytics",
        lambda _youtube, _analytics, _start, _end: {
            "window": {
                "start_date": "2026-05-01",
                "end_date": "2026-05-28",
                "lookback_days": 28,
            },
            "summary": {
                "views": 321,
                "estimatedMinutesWatched": 654,
                "averageViewDuration": 33.0,
                "likes": 21,
                "comments": 5,
                "shares": 3,
                "subscribersGained": 2,
                "subscribersLost": 1,
            },
            "top_videos": [
                {
                    "video": "vid1",
                    "title": "How to Stay Calm in Meetings",
                    "views": 111,
                    "estimatedMinutesWatched": 222,
                    "averageViewDuration": 31.5,
                    "likes": 10,
                    "comments": 1,
                    "shares": 1,
                    "subscribersGained": 1,
                }
            ],
            "traffic_sources": [
                {"insightTrafficSourceType": "SHORTS", "views": 300, "estimatedMinutesWatched": 600}
            ],
            "subscribed_status": [
                {"subscribedStatus": "UNSUBSCRIBED", "views": 280, "estimatedMinutesWatched": 550}
            ],
            "device_type": [{"deviceType": "MOBILE", "views": 290}],
        },
    )

    result = run(workspace_root=workspace, project_root=project)

    assert Path(result["metrics_md"]).exists()
    assert Path(result["analytics_md"]).exists()
    assert Path(result["snapshot_json"]).exists()
    assert (project / "state" / "ledger_strategy.json").exists()
    assert (project / "state" / "ledger_topic_plan.json").exists()

    analytics_md = Path(result["analytics_md"]).read_text(encoding="utf-8")
    assert "SHORTS" in analytics_md
    assert "UNSUBSCRIBED" in analytics_md
