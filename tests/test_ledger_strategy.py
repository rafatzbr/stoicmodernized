from pathlib import Path

from src.ledger_strategy import LedgerStrategyManager


def test_load_topic_ideas_reads_and_refreshes_file(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    artifacts = workspace / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)
    (artifacts / "stoic-modernized-council-plan-2026-05-10.md").write_text(
        "# Plan\n- 4 discovery videos\n- 3 conversion videos\n",
        encoding="utf-8",
    )

    manager = LedgerStrategyManager(project_root=tmp_path, workspace_root=workspace)

    payload = manager.load_topic_plan(niche="modern work")

    assert manager.topic_plan_path.exists()
    assert manager.topic_ideas_path.exists()
    assert payload["niche"] == "modern work"
    assert payload["batches"]["discovery"][0]["objective"] == "discovery"
    assert payload["strategy_generated_at"]

    cached = manager.load_topic_plan(niche="modern work")
    assert cached["generated_at"] == payload["generated_at"]


def test_build_job_packet_includes_steering_fields(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    (workspace / "artifacts").mkdir(parents=True, exist_ok=True)
    manager = LedgerStrategyManager(project_root=tmp_path, workspace_root=workspace)

    from src.config import Channel, VideoMode

    packet = manager.build_job_packet(
        job_id="job-123",
        topic="work anxiety",
        channel=Channel.STOIC_MODERNIZED,
        video_mode=VideoMode.SHORT,
    )

    assert packet["objective"] == "conversion"
    assert packet["packaging_angle"]
    assert packet["title_formulas"]
    assert packet["avoid_angles"]
    assert packet["experiment_hypothesis"]


def test_global_strategy_derives_metric_signals_from_youtube_and_tiktok(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    artifacts = workspace / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)
    (artifacts / "stoic-modernized-youtube-metrics-2026-05-17.md").write_text(
        """
# YouTube metrics
- Subscribers gained: 2
## Traffic sources
- SHORTS: 1,200 views, 90 minutes
- YT_SEARCH: 20 views, 14 minutes
## Device type
- MOBILE: 900 views
- DESKTOP: 100 views
## Subscribed status
- UNSUBSCRIBED: 950 views
- SUBSCRIBED: 50 views
## Top videos
1. How to Stay Calm in Meetings - 111 views
""",
        encoding="utf-8",
    )
    (artifacts / "stoic-modernized-facebook-metrics-2026-05-18.md").write_text(
        """
# Facebook metrics
## Analytics window
- Page video views: 333
- Page post engagements: 44
- Page unique impressions/reach: 222
## Top Facebook videos by lifetime views
1. Stop Playing Status Games At Work
   - Views: 150
""",
        encoding="utf-8",
    )
    (artifacts / "stoic-modernized-tiktok-analytics-2026-05-18.md").write_text(
        """
# TikTok analytics
## Strongest posts by views
1. Your colleague's disrespect isn't stealing your peace...
   - Views: 693
2. Strategic Patience: The Ultimate Workplace Power Move
   - Views: 564
## Recommended weighting for next batch
- 40% conflict / disrespect / status games
- 35% strategic patience / leverage / timing
- 25% discipline / focus / overexplaining
""",
        encoding="utf-8",
    )

    manager = LedgerStrategyManager(project_root=tmp_path, workspace_root=workspace)
    strategy = manager.generate_global_strategy()

    signals = strategy["metric_signals"]
    assert signals["platform"]["youtube_shorts_views"] == 1200
    assert signals["platform"]["facebook_video_views"] == 333
    assert signals["platform"]["facebook_post_engagements"] == 44
    assert signals["facebook_top_titles"] == ["Stop Playing Status Games At Work"]
    assert signals["platform"]["mobile_view_share"] == 0.9
    assert signals["platform"]["unsubscribed_view_share"] == 0.95
    assert signals["tiktok_weightings"][0]["label"] == "conflict / disrespect / status games"
    assert "conflict / disrespect / status games" in signals["winning_themes"]
    assert "optimize for cold/unsubscribed viewers" in " ".join(strategy["format_steering"])
    assert strategy["content_lanes"]["conversion"]["share"] >= 3

    plan = manager.generate_topic_plan()
    assert plan["metric_signals"]["source_count"] == 3
    assert plan["ideas"][0]["metric_signal"] == "conflict / disrespect / status games"
    assert plan["ideas"][0]["title"] == "Your Coworker's Disrespect Only Wins If You React"


def test_topic_plan_uses_new_tiktok_weighting_themes(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    artifacts = workspace / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)
    (artifacts / "stoic-modernized-tiktok-analytics-2026-05-23.md").write_text(
        """
# TikTok analytics
## Recommended weighting for next batch
- 35% approval pressure / disagreement / seeking validation
- 25% deadline rushing / pressure spirals / urgency
- 20% strategic patience / decision pause / restraint
- 15% coworker disrespect / passive aggression / reactivity
""",
        encoding="utf-8",
    )

    manager = LedgerStrategyManager(project_root=tmp_path, workspace_root=workspace)
    plan = manager.generate_topic_plan()

    titles = [idea["title"] for idea in plan["ideas"][:5]]
    assert "You Do Not Need Everyone at Work to Like You" in titles
    assert "Why Rushing Makes Work Pressure Worse" in titles
    assert "Strategic Patience Is a Workplace Power Move" in titles
    assert "Your Coworker's Disrespect Only Wins If You React" in titles
    assert plan["metric_signals"]["tiktok_weightings"][0]["label"] == "approval pressure / disagreement / seeking validation"


def test_topic_plan_uses_workplace_chaos_tiktok_weighting(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    artifacts = workspace / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)
    (artifacts / "stoic-modernized-tiktok-analytics-2026-06-01.md").write_text(
        """
# TikTok analytics
## Analytics window
- Video views: 1,471
- Profile views: 4
- Likes: 69
- Comments: 9
- Shares: 2
- Followers at window end: 56
- Followers gained: 11
## Strongest posts by views
1. Stop Cleaning Their Mess - 435 views
2. Your boss shifts priorities at 4 PM on Friday - 208 views
## Recommended weighting for next batch
- 35% workplace chaos / cleaning others' mess / boundary triggers
- 25% strategic patience / rushing / decision pause
""",
        encoding="utf-8",
    )

    manager = LedgerStrategyManager(project_root=tmp_path, workspace_root=workspace)
    strategy = manager.generate_global_strategy()
    signals = strategy["metric_signals"]

    assert signals["tiktok_top_titles"] == ["Stop Cleaning Their Mess", "Your boss shifts priorities at 4 PM on Friday"]
    assert signals["tiktok_weightings"][0]["label"] == "workplace chaos / cleaning others' mess / boundary triggers"
    assert "workplace chaos / cleaning others' mess / boundary triggers" in signals["winning_themes"]

    plan = manager.generate_topic_plan()
    assert plan["metric_signals"]["source_count"] == 1
    assert plan["ideas"][0]["title"] == "Their Mess Is Not Your Emergency"
    assert plan["ideas"][0]["metric_signal"] == "workplace chaos / cleaning others' mess / boundary triggers"


def test_job_packet_carries_metric_and_format_steering(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    artifacts = workspace / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)
    (artifacts / "stoic-modernized-tiktok-metrics-2026-05-18.md").write_text(
        """
# Manual TikTok metrics
## Recommended weighting for next batch
- 40% conflict / disrespect / status games
""",
        encoding="utf-8",
    )
    manager = LedgerStrategyManager(project_root=tmp_path, workspace_root=workspace)

    from src.config import Channel, VideoMode

    packet = manager.build_job_packet(
        job_id="job-456",
        topic="coworker disrespect",
        channel=Channel.STOIC_MODERNIZED,
        video_mode=VideoMode.SHORT,
    )

    assert packet["metric_signals"]["tiktok_weightings"]
    assert packet["format_steering"]
    assert any("TikTok" in note for note in packet["distribution_notes"])
