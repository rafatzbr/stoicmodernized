from __future__ import annotations

from pathlib import Path
from typing import Any

from src import refresh_facebook_metrics as fb


class FakeResponse:
    def __init__(self, payload: dict[str, Any]):
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return self.payload


def test_refresh_facebook_metrics_writes_artifacts_and_regenerates_ledger(monkeypatch, tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    project_root = tmp_path / "project"
    project_root.mkdir()

    monkeypatch.setattr(fb.settings, "meta_graph_api_version", "v25.0", raising=False)
    monkeypatch.setattr(fb.settings, "meta_page_access_token", "USER_OR_SYSTEM_TOKEN", raising=False)
    monkeypatch.setattr(fb.settings, "facebook_page_id", "page-1", raising=False)

    def fake_get(url: str, params: dict[str, Any], timeout: int = 30) -> FakeResponse:
        if url.endswith("/page-1") and params.get("fields") == "access_token":
            return FakeResponse({"access_token": "PAGE_TOKEN"})
        if url.endswith("/page-1"):
            assert params["access_token"] == "PAGE_TOKEN"
            return FakeResponse({"id": "page-1", "name": "Stoic Modernized", "followers_count": 10, "fan_count": 9, "link": "https://facebook.test/page"})
        if url.endswith("/page-1/insights"):
            assert params["access_token"] == "PAGE_TOKEN"
            return FakeResponse(
                {
                    "data": [
                        {"name": "page_video_views", "values": [{"value": 12}, {"value": 8}]},
                        {"name": "page_post_engagements", "values": [{"value": 5}]},
                        {"name": "page_impressions_unique", "values": [{"value": 20}]},
                    ]
                }
            )
        if url.endswith("/page-1/videos"):
            return FakeResponse(
                {
                    "data": [
                        {
                            "id": "video-1",
                            "title": "Your Coworker's Disrespect Only Wins If You React",
                            "created_time": "2026-05-24T00:00:00+0000",
                            "permalink_url": "https://facebook.test/video-1",
                        }
                    ]
                }
            )
        if url.endswith("/video-1/video_insights"):
            return FakeResponse(
                {
                    "data": [
                        {"name": "total_video_views", "values": [{"value": 33}]},
                        {"name": "total_video_10s_views", "values": [{"value": 22}]},
                        {"name": "total_video_complete_views", "values": [{"value": 11}]},
                        {"name": "total_video_avg_time_watched", "values": [{"value": 7}]},
                    ]
                }
            )
        raise AssertionError(f"unexpected URL: {url}")

    monkeypatch.setattr(fb.requests, "get", fake_get)

    result = fb.run(lookback_days=7, workspace_root=workspace, project_root=project_root, video_limit=5)

    metrics_md = Path(result["metrics_md"])
    snapshot_json = Path(result["snapshot_json"])
    assert metrics_md.exists()
    assert snapshot_json.exists()
    metrics = metrics_md.read_text(encoding="utf-8")
    assert "Page video views: 20" in metrics
    assert "Page post engagements: 5" in metrics
    assert "Your Coworker's Disrespect Only Wins If You React" in metrics
    assert (project_root / "state" / "ledger_strategy.json").exists()
    assert (project_root / "state" / "ledger_topic_plan.json").exists()
