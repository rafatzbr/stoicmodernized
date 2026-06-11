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


def test_load_topic_plan_refreshes_stale_cache_without_umbrella_policy(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    (workspace / "artifacts").mkdir(parents=True, exist_ok=True)
    manager = LedgerStrategyManager(project_root=tmp_path, workspace_root=workspace)
    strategy = manager.load_global_strategy()
    manager.topic_plan_path.write_text(
        '{"niche":"stoicism for modern workers","strategy_generated_at":"'
        + strategy["generated_at"]
        + '","ideas":[{"title":"Why Your Anxiety Wants a Script"}]}',
        encoding="utf-8",
    )

    refreshed = manager.load_topic_plan()

    assert refreshed["subject_umbrella_policy"]
    assert refreshed["ideas"][0].get("subject_umbrella")


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
    leading_titles = [idea["title"] for idea in plan["ideas"][:6]]
    assert "When the Review Comment Feels Personal" in leading_titles
    assert any(idea.get("metric_signal") == "conflict / disrespect / status games" for idea in plan["ideas"][:6])


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

    titles = [idea["title"] for idea in plan["ideas"][:8]]
    assert "When the Review Comment Feels Personal" in titles
    assert "When the Export Timestamp Is Stale" in titles
    assert "Strategic Patience Is a Workplace Power Move" in titles
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
    handoff = next(idea for idea in plan["ideas"] if idea["title"] == "When the Handoff Has No Owner")
    assert handoff["metric_signal"] == "workplace chaos / cleaning others' mess / boundary triggers"
    assert plan["ideas"][0]["subject_umbrella"] != "loss_of_control"


def test_topic_plan_maps_concrete_operational_weighting_to_fresh_process_subjects(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    artifacts = workspace / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)
    (artifacts / "stoic-modernized-tiktok-analytics-2026-06-07.md").write_text(
        """
# TikTok analytics
## Recommended weighting for next batch
- 35% concrete operational frictions / ordinary objects
- 25% criticism / feedback without defensiveness
- 20% attention-control systems
- 10% resource constraints / doing useful work with less
- 10% ambition / promotion / desire control
""",
        encoding="utf-8",
    )

    manager = LedgerStrategyManager(project_root=tmp_path, workspace_root=workspace)
    plan = manager.generate_topic_plan()

    titles = [idea["title"] for idea in plan["ideas"]]
    assert "When the Dashboard Filter Is Wrong" in titles
    assert "When the Version Label Is Stale" in titles
    assert "When the Client Note Needs One Clarifying Question" in titles
    assert "When the Calendar Block Gets Broken" in titles
    first_five = titles[:5]
    assert "When the Review Comment Feels Personal" not in first_five
    assert "When the Checklist Has One Missing Step" not in first_five
    assert plan["metric_signals"]["tiktok_weightings"][0]["label"] == "concrete operational frictions / ordinary objects"


def test_topic_plan_carries_subject_umbrellas_and_rotates_first_week(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    (workspace / "artifacts").mkdir(parents=True, exist_ok=True)

    manager = LedgerStrategyManager(project_root=tmp_path, workspace_root=workspace)
    plan = manager.generate_topic_plan()

    first_eight = plan["ideas"][:8]
    umbrellas = [idea.get("subject_umbrella") for idea in first_eight]
    assert all(umbrellas)
    assert len(set(umbrellas)) >= 4
    assert all(idea.get("operational_trigger") for idea in first_eight)
    assert all(idea.get("subject_family") for idea in first_eight)


def test_topic_plan_generates_broad_candidate_pool_before_whiskers_selection(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    (workspace / "artifacts").mkdir(parents=True, exist_ok=True)

    manager = LedgerStrategyManager(project_root=tmp_path, workspace_root=workspace)
    plan = manager.generate_topic_plan()

    ideas = plan["ideas"]
    umbrellas = [idea["subject_umbrella"] for idea in ideas]
    triggers = [idea["operational_trigger"] for idea in ideas]
    leading_umbrellas = umbrellas[:12]

    assert len(ideas) >= 24
    assert len(set(umbrellas)) >= 8
    assert len(set(triggers)) >= 20
    assert max(leading_umbrellas.count(umbrella) for umbrella in set(leading_umbrellas)) <= 2


def test_topic_variety_metadata_handles_new_trigger_phrasings(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    (workspace / "artifacts").mkdir(parents=True, exist_ok=True)

    manager = LedgerStrategyManager(project_root=tmp_path, workspace_root=workspace)
    plan = manager.generate_topic_plan()
    by_title = {idea["title"]: idea for idea in plan["ideas"]}

    assert by_title["When the Data Import Fails Twice"]["subject_umbrella"] == "loss_of_control"
    assert by_title["When the Automation Breaks at the Worst Time"]["operational_trigger"] == "automation breaks"
    assert by_title["When the Workspace Noise Won't Stop"]["subject_umbrella"] == "everyday_inconvenience"
    assert by_title["When They Ask for an Answer Before You Verify"]["operational_trigger"] == "answer before you verify"


def test_topic_plan_deprioritizes_loss_of_control_in_leading_slate(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    artifacts = workspace / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)
    (artifacts / "stoic-modernized-tiktok-metrics-2026-06-09.md").write_text(
        """
# Manual TikTok metrics
## Recommended weighting for next batch
- 35% concrete operational frictions / ordinary objects
- 20% attention-control systems
- 10% ambition / promotion / desire control
""",
        encoding="utf-8",
    )

    manager = LedgerStrategyManager(project_root=tmp_path, workspace_root=workspace)
    plan = manager.generate_topic_plan()

    leading_umbrellas = [idea.get("subject_umbrella") for idea in plan["ideas"][:4]]
    assert "loss_of_control" not in leading_umbrellas
    assert len(set(leading_umbrellas)) == 4
    assert plan["umbrella_rotation_version"] == 3


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
