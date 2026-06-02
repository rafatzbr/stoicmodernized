import json
from pathlib import Path

import pytest

import src.main as main
from src.stages.social_distribution import SocialDistributionStage, build_social_captions


def _write_job_artifacts(job_dir: Path) -> None:
    job_dir.mkdir(parents=True, exist_ok=True)
    video_path = job_dir / "remotion_output.mp4"
    video_path.write_bytes(b"fake mp4")
    metadata_dir = job_dir / "metadata"
    metadata_dir.mkdir()
    (metadata_dir / "metadata.json").write_text(
        json.dumps(
            {
                "title": "Stop Resenting Last Minute Priority Shifts | Stoic Modernized",
                "description": (
                    "A last-minute priority shift can either steal your focus or become practice. "
                    "Ask what matters most, then execute.\n\n"
                    "Resources:\n- Book link\n\n"
                    "Subscribe to @stoic-modernized for practical Stoic tools you can use at work."
                ),
                "tags": ["stoicism", "workplace stress", "career advice", "priority shifts"],
            }
        ),
        encoding="utf-8",
    )


def test_build_social_captions_are_platform_specific_and_do_not_include_youtube_resources() -> None:
    metadata = {
        "title": "Stop Resenting Last Minute Priority Shifts | Stoic Modernized",
        "description": (
            "A last-minute priority shift can either steal your focus or become practice. "
            "Ask what matters most, then execute.\n\n"
            "Resources:\n- Book link\n\n"
            "Subscribe to @stoic-modernized for practical Stoic tools you can use at work."
        ),
        "tags": ["stoicism", "workplace stress", "career advice", "priority shifts"],
    }

    captions = build_social_captions(metadata, channel_name="Stoic Modernized")

    assert set(captions) == {"tiktok", "instagram", "facebook"}
    for caption in captions.values():
        assert "Resources:" not in caption
        assert "Subscribe to" not in caption
        assert "#StoicModernized" in caption
    assert len(captions["tiktok"]) <= 2200
    assert "#PriorityShifts" in captions["instagram"]
    assert captions["facebook"].startswith("A last-minute priority shift")


def test_media_explorer_caption_limits_hashtags_to_relevant_five() -> None:
    metadata = {
        "title": "Stop The Reopened Decision Loop At Work | Stoic Modernized",
        "description": (
            "When a decision keeps getting reopened at work, your job is not to win the argument again. "
            "Pause, restate the boundary, and protect your focus for the next useful move.\n\n"
            "#stoicism #stoicmodernized #workplacestress #careeradvice #selfcontrol"
        ),
        "tags": [
            "anxiety spiral",
            "bad meetings",
            "credit stealing at work",
            "stoicism",
            "stoic modernized",
            "decision making at work",
            "focus at work",
            "pause before reacting",
            "workplace stress",
        ],
    }

    captions = build_social_captions(metadata, channel_name="Stoic Modernized")
    instagram = captions["instagram"]
    hashtags = [word for word in instagram.split() if word.startswith("#")]

    assert len(hashtags) <= 5
    assert "#stoicism" not in instagram
    assert "#workplacestress" not in instagram
    assert hashtags == ["#Stoicism", "#StoicModernized", "#WorkplaceStress", "#CareerAdvice", "#SelfControl"]
    assert "#AnxietySpiral" not in hashtags
    assert "#BadMeetings" not in hashtags
    assert "#CreditStealingAtWork" not in hashtags


def test_mock_social_distribution_writes_auditable_manifest(monkeypatch, tmp_path: Path) -> None:
    jobs_dir = tmp_path / "jobs"
    job_dir = jobs_dir / "job-123"
    _write_job_artifacts(job_dir)
    monkeypatch.setattr("src.stages.social_distribution.settings.jobs_dir", jobs_dir)
    monkeypatch.setattr("src.stages.social_distribution.settings.social_video_public_base_url", "https://media.example.test", raising=False)

    result = SocialDistributionStage(job_id="job-123", mock=True).run()

    assert result["job_id"] == "job-123"
    assert result["status"] == "mock_completed"
    assert result["video_path"].endswith("remotion_output.mp4")
    assert result["public_video_url"] == "https://media.example.test/job-123/remotion_output.mp4"
    assert {platform["platform"] for platform in result["platforms"]} == {"tiktok", "instagram", "facebook"}
    assert all(platform["status"] == "mock_uploaded" for platform in result["platforms"])
    manifest_path = job_dir / "distribution" / "social_uploads.json"
    assert manifest_path.exists()
    saved = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert saved["captions"]["tiktok"] == result["captions"]["tiktok"]
    page_path = jobs_dir.parent / "social_public" / "job-123" / "index.html"
    assert page_path.exists()
    assert result["manual_instagram_page_url"] == "https://media.example.test/job-123/"
    page_html = page_path.read_text(encoding="utf-8")
    assert "REEL<br>PACKAGE" not in page_html
    assert "Instagram Semi-Manual Upload Kit" not in page_html
    assert "<video controls" in page_html
    assert "Copy Title" in page_html
    assert "Copy Description" in page_html
    assert "Stop Resenting Last Minute Priority Shifts" in page_html


def test_metadata_command_always_publishes_video_to_media_explorer(monkeypatch, tmp_path: Path) -> None:
    jobs_dir = tmp_path / "jobs"
    job_dir = jobs_dir / "job-654"
    _write_job_artifacts(job_dir)
    script_path = job_dir / "script" / "script.json"
    script_path.parent.mkdir()
    script_path.write_text("{}", encoding="utf-8")
    monkeypatch.setattr("src.stages.social_distribution.settings.jobs_dir", jobs_dir)
    monkeypatch.setattr(main.settings, "jobs_dir", jobs_dir)
    monkeypatch.setattr(main.settings, "social_video_public_base_url", "https://stoicmodernized.zweb.ca", raising=False)
    monkeypatch.setattr(main, "print_header", lambda: None)
    monkeypatch.setattr(
        main,
        "_load_job_record",
        lambda job_id: type(
            "JobRecord",
            (),
            {"job_id": job_id, "script_path": str(script_path), "video_path": str(job_dir / "remotion_output.mp4")},
        )(),
    )
    metadata_payload = {
        "title": "Stop Resenting Last Minute Priority Shifts | Stoic Modernized",
        "description": "A last-minute shift can become practice.",
        "tags": ["stoicism", "workplace stress"],
    }
    monkeypatch.setattr(main, "_generate_metadata_payload_for_job", lambda **kwargs: metadata_payload)

    def fake_save_metadata(job_id: str, payload: dict) -> Path:
        metadata_dir = jobs_dir / job_id / "metadata"
        metadata_dir.mkdir(parents=True, exist_ok=True)
        metadata_path = metadata_dir / "metadata.json"
        metadata_path.write_text(json.dumps(payload), encoding="utf-8")
        return metadata_path

    monkeypatch.setattr(main, "_save_metadata", fake_save_metadata)
    monkeypatch.setattr(main, "_save_covered_news", lambda job_id, title: None)

    main.metadata(job_id="job-654", mock=True)

    public_dir = jobs_dir.parent / "social_public"
    public_video = public_dir / "job-654" / "remotion_output.mp4"
    page_path = public_dir / "job-654" / "index.html"
    explorer_path = public_dir / "videos.html"
    assert public_video.read_bytes() == b"fake mp4"
    assert page_path.exists()
    page_html = page_path.read_text(encoding="utf-8")
    assert "<video controls" in page_html
    assert "https://stoicmodernized.zweb.ca/job-654/remotion_output.mp4" in page_html
    assert explorer_path.exists()
    explorer_html = explorer_path.read_text(encoding="utf-8")
    assert "job-654" in explorer_html
    assert "remotion_output.mp4" in explorer_html
    assert '"title":"Stop Resenting Last Minute Priority Shifts"' in explorer_html
    assert explorer_html.count('"title":"Stop Resenting Last Minute Priority Shifts"') == 2
    assert "function displayName(item)" in explorer_html
    assert "let sortKey = 'modified'; let sortDir = 'desc';" in explorer_html
    assert "function matchesQuery(item, q)" in explorer_html
    assert "grid-template-columns:minmax(0,1fr)" in explorer_html
    assert ".label{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" in explorer_html
    assert ".sub{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" in explorer_html


def test_distribute_command_updates_job_status(monkeypatch, tmp_path: Path) -> None:
    jobs_dir = tmp_path / "jobs"
    job_dir = jobs_dir / "job-789"
    _write_job_artifacts(job_dir)
    monkeypatch.setattr("src.stages.social_distribution.settings.jobs_dir", jobs_dir)
    monkeypatch.setattr(main.settings, "jobs_dir", jobs_dir)
    monkeypatch.setattr(main, "print_header", lambda: None)
    monkeypatch.setattr(main, "_load_job_record", lambda job_id: type("JobRecord", (), {"job_id": job_id})())
    updates = []
    monkeypatch.setattr(main.db, "update_job", lambda *args, **kwargs: updates.append((args, kwargs)))

    main.distribute(job_id="job-789", mock=True, platforms="instagram,facebook")

    assert updates[-1][0][0] == "job-789"
    assert updates[-1][1]["status"] == "social_distributed"
    manifest = json.loads((job_dir / "distribution" / "social_uploads.json").read_text(encoding="utf-8"))
    assert {entry["platform"] for entry in manifest["platforms"]} == {"instagram", "facebook"}


class Response:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code
        self.text = json.dumps(payload)

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(self.text)


def test_facebook_upload_resolves_page_token_before_posting(monkeypatch, tmp_path: Path) -> None:
    jobs_dir = tmp_path / "jobs"
    job_dir = jobs_dir / "job-fb"
    _write_job_artifacts(job_dir)
    monkeypatch.setattr("src.stages.social_distribution.settings.jobs_dir", jobs_dir)
    monkeypatch.setattr("src.stages.social_distribution.settings.meta_graph_api_version", "v24.0", raising=False)
    monkeypatch.setattr("src.stages.social_distribution.settings.meta_page_access_token", "USER_TOKEN", raising=False)
    monkeypatch.setattr("src.stages.social_distribution.settings.facebook_page_id", "page-1", raising=False)
    monkeypatch.setattr("src.stages.social_distribution.settings.meta_app_id", None, raising=False)
    monkeypatch.setattr("src.stages.social_distribution.settings.meta_app_secret", None, raising=False)

    seen = {}

    def fake_get(url, params, timeout):
        seen["get"] = {"url": url, "params": params, "timeout": timeout}
        return Response({"access_token": "PAGE_TOKEN"})

    def fake_post(url, files, data, timeout):
        seen["post"] = {"url": url, "data": data, "timeout": timeout, "file_closed": files["source"].closed}
        return Response({"id": "fb-video-1"})

    monkeypatch.setattr("src.stages.social_distribution.requests.get", fake_get)
    monkeypatch.setattr("src.stages.social_distribution.requests.post", fake_post)

    result = SocialDistributionStage(job_id="job-fb", platforms=["facebook"]).run()

    assert result["status"] == "completed"
    assert result["platforms"][0]["post_id"] == "fb-video-1"
    assert "get" in seen
    assert seen["get"]["params"]["access_token"] == "USER_TOKEN"
    assert seen["post"]["data"]["access_token"] == "PAGE_TOKEN"


def test_facebook_upload_refreshes_meta_token_and_persists_it_before_page_resolution(monkeypatch, tmp_path: Path) -> None:
    jobs_dir = tmp_path / "jobs"
    job_dir = jobs_dir / "job-fb-refresh"
    _write_job_artifacts(job_dir)
    env_file = tmp_path / ".env"
    env_file.write_text("META_PAGE_ACCESS_TOKEN=OLD_USER_TOKEN\nFACEBOOK_PAGE_ID=page-1\n", encoding="utf-8")
    monkeypatch.setattr("src.stages.social_distribution.ENV_FILE", env_file)
    monkeypatch.setattr("src.stages.social_distribution.settings.jobs_dir", jobs_dir)
    monkeypatch.setattr("src.stages.social_distribution.settings.meta_graph_api_version", "v24.0", raising=False)
    monkeypatch.setattr("src.stages.social_distribution.settings.meta_page_access_token", "OLD_USER_TOKEN", raising=False)
    monkeypatch.setattr("src.stages.social_distribution.settings.facebook_page_id", "page-1", raising=False)
    monkeypatch.setattr("src.stages.social_distribution.settings.meta_app_id", "app-123", raising=False)
    monkeypatch.setattr("src.stages.social_distribution.settings.meta_app_secret", "secret-456", raising=False)

    seen = {"gets": []}

    def fake_get(url, params, timeout):
        seen["gets"].append({"url": url, "params": params, "timeout": timeout})
        if url.endswith("/oauth/access_token"):
            return Response({"access_token": "REFRESHED_USER_TOKEN", "expires_in": 5184000})
        return Response({"access_token": "PAGE_TOKEN"})

    def fake_post(url, files, data, timeout):
        seen["post"] = {"url": url, "data": data, "timeout": timeout}
        return Response({"id": "fb-video-2"})

    monkeypatch.setattr("src.stages.social_distribution.requests.get", fake_get)
    monkeypatch.setattr("src.stages.social_distribution.requests.post", fake_post)

    result = SocialDistributionStage(job_id="job-fb-refresh", platforms=["facebook"]).run()

    assert result["status"] == "completed"
    assert result["platforms"][0]["post_id"] == "fb-video-2"
    assert seen["gets"][0]["params"] == {
        "grant_type": "fb_exchange_token",
        "client_id": "app-123",
        "client_secret": "secret-456",
        "fb_exchange_token": "OLD_USER_TOKEN",
    }
    assert seen["gets"][1]["params"]["access_token"] == "REFRESHED_USER_TOKEN"
    assert seen["post"]["data"]["access_token"] == "PAGE_TOKEN"
    assert "META_PAGE_ACCESS_TOKEN=REFRESHED_USER_TOKEN" in env_file.read_text(encoding="utf-8")


def test_real_social_distribution_reports_missing_credentials_without_uploading(monkeypatch, tmp_path: Path) -> None:
    jobs_dir = tmp_path / "jobs"
    job_dir = jobs_dir / "job-456"
    _write_job_artifacts(job_dir)
    monkeypatch.setattr("src.stages.social_distribution.settings.jobs_dir", jobs_dir)
    monkeypatch.setattr("src.stages.social_distribution.settings.meta_page_access_token", None, raising=False)
    monkeypatch.setattr("src.stages.social_distribution.settings.instagram_user_id", None, raising=False)
    monkeypatch.setattr("src.stages.social_distribution.settings.facebook_page_id", None, raising=False)
    monkeypatch.setattr("src.stages.social_distribution.settings.tiktok_access_token", None, raising=False)

    result = SocialDistributionStage(job_id="job-456", mock=False).run()

    assert result["status"] == "needs_configuration"
    by_platform = {entry["platform"]: entry for entry in result["platforms"]}
    assert by_platform["instagram"]["status"] == "missing_credentials"
    assert by_platform["facebook"]["status"] == "missing_credentials"
    assert by_platform["tiktok"]["status"] == "missing_credentials"
    assert all("missing" in entry["error"].lower() for entry in result["platforms"])
