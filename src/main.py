"""Main CLI entry point for stoic-modernized."""

import asyncio
import contextlib
import io
import re
import shutil
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from src.config import Channel, RemotionPlatform, VideoMode, settings
import os, json, tempfile, pathlib
from src.database import db
from src.ledger_strategy import LedgerStrategyManager
from src.logging_config import JobLogger
from src.models import Scene, VideoRenderConfig
from src.news_registry import news_registry
from src.stages.images import ImageGenerationError, ImageGenerationStage
from src.stages.music import BackgroundMusicStage
from src.stages.quality_gate import QualityGateError, QualityGateStage
from src.stages.render import VideoRenderer
from src.stages.remotion_renderer import RemotionRenderer
from src.stages.research import ResearchStage
from src.stages.scenes import SceneStage
from src.stages.script import ScriptGenerationError, ScriptStage
from src.stages.subtitles import SubtitleStage
from src.stages.social_distribution import SocialDistributionStage, publish_media_explorer_artifacts
from src.stages.tts import TTSStage
from src.stages.narration_prep import NarrationPreparationStage
from src.stages.upload import YouTubeUploader
from src.utils import get_job_dir, load_json, save_json

app = typer.Typer(
    name="stoic-modernized",
    help="Automate faceless YouTube video creation for Stoicism channel.",
    add_completion=False,
)

console = Console()


class TeeTextIO(io.TextIOBase):
    """Mirror writes to multiple text streams."""

    def __init__(self, *streams: io.TextIOBase):
        self.streams = streams

    def write(self, s: str) -> int:
        for stream in self.streams:
            try:
                stream.write(s)
            except ValueError:
                continue
        return len(s)

    def flush(self) -> None:
        for stream in self.streams:
            try:
                stream.flush()
            except ValueError:
                continue


@contextlib.contextmanager
def job_output_capture(job_id: str):
    """Persist stdout/stderr for a job while preserving normal console output."""
    log_dir = settings.jobs_dir / job_id
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{job_id}.log"
    db.update_job(job_id, log_path=str(log_path))

    with log_path.open("a", encoding="utf-8") as log_file:
        tee_out = TeeTextIO(sys.stdout, log_file)
        tee_err = TeeTextIO(sys.stderr, log_file)
        with contextlib.redirect_stdout(tee_out), contextlib.redirect_stderr(tee_err):
            yield log_path


def print_header() -> None:
    """Print application header."""
    console.print(
        "[bold magenta]╔═══════════════════════════════════════════════════════════╗[/bold magenta]"
    )
    console.print(
        "[bold magenta]║[/bold magenta]    [bold white]Stoic Modernized[/bold white] - YouTube Video Automation    [bold magenta]║[/bold magenta]"
    )
    console.print(
        "[bold magenta]╚═══════════════════════════════════════════════════════════╝[/bold magenta]"
    )
    console.print()


def print_job_table(jobs: list) -> None:
    """Print jobs in a table format."""
    table = Table(title="Pipeline Jobs")
    table.add_column("Job ID", style="cyan")
    table.add_column("Topic", style="white")
    table.add_column("Status", style="green")
    table.add_column("Created", style="dim")

    for job in jobs:
        table.add_row(
            job.job_id[:8] + "...",
            job.topic[:40] + "..." if len(job.topic) > 40 else job.topic,
            job.status,
            job.created_at.strftime("%Y-%m-%d %H:%M"),
        )

    console.print(table)


def _terminate_process(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def _load_job_record(job_id: str):
    job_record = db.get_job(job_id)
    if not job_record:
        console.print(f"[red]Error: Job {job_id} not found[/red]")
        raise typer.Exit(code=1)
    return job_record


def _mark_stage_failed(job_id: str, stage_name: str, error: object) -> str:
    """Persist a stage failure before exiting a CLI command."""
    error_text = str(error)
    db.update_job(job_id, status=f"{stage_name}_failed", error_message=error_text)
    return error_text


def _exit_stage_failed(job_id: str, stage_name: str, error: object, title: str) -> None:
    error_text = _mark_stage_failed(job_id, stage_name, error)
    console.print()
    console.print(f"[bold red]{title} Failed![/bold red]")
    console.print(f"[dim]Reason:[/dim] {error_text}")
    raise typer.Exit(code=1)


def _save_metadata(job_id: str, metadata_payload: dict) -> Path:
    metadata_dir = get_job_dir(job_id) / "metadata"
    metadata_dir.mkdir(parents=True, exist_ok=True)
    metadata_path = metadata_dir / "metadata.json"
    save_json(metadata_payload, metadata_path)
    db.update_job(job_id, status="metadata_complete", metadata_path=str(metadata_path))
    return metadata_path


def _generate_metadata_payload_for_job(job_id: str, job_record, channel: Optional[Channel] = None, mock: bool = False) -> dict:
    """Regenerate metadata from the current script artifact for a job."""
    if not job_record.script_path:
        raise ValueError("No script found for this job")

    video_mode = _resolve_video_mode(job_id=job_id)
    script_data = _normalize_script_for_video_mode(load_json(Path(job_record.script_path)), video_mode)
    resolved_channel = _resolve_channel(channel, job_id)
    uploader = YouTubeUploader(mock=mock, channel=resolved_channel)
    # Mock metadata is used by guardrail validation inside later pipeline stages.
    # Keep it strictly local/deterministic: passing narration triggers AI
    # description generation, which can hang on the local LLM after script/scene
    # work has already completed.
    script_text = None if mock else script_data.get("narration", "")

    return uploader.generate_metadata(
        script_title=script_data["title"],
        chapters=script_data.get("chapters", []),
        script_text=script_text,
        job_dir=str(get_job_dir(job_id)),
    )


def _save_covered_news(job_id: str, video_title: str) -> int:
    context = _load_job_context(job_id)
    try:
        channel = Channel(context.get("channel", settings.default_channel.value))
    except Exception:
        channel = settings.default_channel

    # AI Signal channel removed - this function not needed for Stoic Modernized
    return 0

    job_record = db.get_job(job_id)
    if not job_record or not job_record.research_path:
        return 0

    research_data = load_json(Path(job_record.research_path))
    sources = research_data.get("sources", [])
    entries = news_registry.build_entries_for_job(
        job_id=job_id,
        channel=channel,
        topic=context.get("topic") or research_data.get("topic") or "",
        video_title=video_title,
        sources=sources,
    )
    return news_registry.add_entries(channel, entries)


def _job_context_path(job_id: str) -> Path:
    return get_job_dir(job_id) / "job.json"


def _load_job_context(job_id: str) -> dict:
    path = _job_context_path(job_id)
    if path.exists():
        try:
            payload = load_json(path)
            if isinstance(payload, dict):
                return payload
        except Exception:
            pass
    channel = settings.default_channel
    return {
        "channel": channel.value,
        "channel_name": settings.get_channel_name(channel),
        "channel_handle": settings.get_channel_handle(channel),
        "channel_description": settings.get_channel_description(channel),
        "channel_voice": settings.get_channel_voice(channel),
    }


def _resolve_channel(channel, job_id: Optional[str] = None) -> Channel:
    # Handle OptionInfo objects from Typer
    if hasattr(channel, 'default'):
        channel = channel.default
    if channel is not None:
        return channel
    if job_id:
        context = _load_job_context(job_id)
        try:
            return Channel(context.get("channel", settings.default_channel.value))
        except Exception:
            return settings.default_channel
    return settings.default_channel


def _default_remotion_platform(mode: str, channel: Channel) -> str:
    """Pick the visual preset that matches the destination surface."""
    if mode != "portrait":
        return "youtube"

    if channel == Channel.STOIC_MODERNIZED:
        return "youtube"

    return "tiktok"


def _resolve_video_mode(video_mode: Optional[VideoMode] = None, job_id: Optional[str] = None) -> VideoMode:
    if video_mode is not None:
        return video_mode
    if job_id:
        context = _load_job_context(job_id)
        try:
            return VideoMode(context.get("video_mode", settings.default_video_mode.value))
        except Exception:
            return settings.default_video_mode
    return settings.default_video_mode


def _short_chapters_from_script(script_data: dict) -> list[dict[str, float | str]]:
    default_titles = ["Hook", "Stoic Principle", "Workplace Application", "CTA"]
    timestamps = [0.0, 12.0, 30.0, 50.0]
    sections = script_data.get("sections") if isinstance(script_data.get("sections"), list) else []
    titles: list[str] = []
    for section in sections[:4]:
        if isinstance(section, dict):
            title = str(section.get("title") or "").strip()
            if title:
                titles.append(title)
    if len(titles) != 4:
        titles = default_titles
    return [{"title": title, "timestamp": ts} for title, ts in zip(titles, timestamps, strict=False)]


def _normalize_script_for_video_mode(script_data: dict, video_mode: VideoMode) -> dict:
    normalized = dict(script_data)
    normalized["video_mode"] = video_mode.value
    if video_mode != VideoMode.SHORT:
        return normalized

    narration = str(script_data.get("narration") or "").strip()
    short_narration = str(script_data.get("short_version") or "").strip()
    narration_word_count = len(narration.split())
    has_timed_blocks = narration.startswith("[") and "\n" in narration
    channel_name = str(script_data.get("channel") or "").strip().lower()
    source_video_mode = str(script_data.get("video_mode") or "").strip().lower()
    already_short_script = source_video_mode == "short" or len(script_data.get("chapters", [])) <= 4



    # Keep authored/timed narration for shorts when it already has structure.
    # Only fall back to short_version when narration is missing or clearly long-form/unstructured.
    if short_narration and (not narration or (not already_short_script and not has_timed_blocks)):
        normalized["narration"] = short_narration
    normalized["chapters"] = _short_chapters_from_script(script_data)
    return normalized


def _persist_job_context(
    job_id: str,
    topic: str,
    channel: Channel,
    video_mode: VideoMode | None = None,
) -> Path:
    existing = _load_job_context(job_id) if _job_context_path(job_id).exists() else {}
    resolved_video_mode = video_mode or VideoMode(existing.get("video_mode", settings.default_video_mode.value))
    payload = {
        "job_id": job_id,
        "topic": topic,
        "channel": channel.value,
        "channel_name": settings.get_channel_name(channel),
        "channel_handle": settings.get_channel_handle(channel),
        "channel_description": settings.get_channel_description(channel),
        "channel_voice": settings.get_channel_voice(channel),
        "video_mode": resolved_video_mode.value,
    }
    return save_json(payload, _job_context_path(job_id))


def _validate_script_subject_before_generation(
    job_id: str,
    job_record,
    channel: Optional[Channel] = None,
    mock: bool = False,
) -> None:
    """Block duplicate/repeated subjects as soon as a script exists.

    Upload still runs the same guardrail as a final safety net, but this prevents
    wasting TTS/image/render work on a script that cannot be published.
    """
    if not getattr(job_record, "script_path", None):
        return

    resolved_channel = _resolve_channel(channel, job_id)
    metadata_payload = _generate_metadata_payload_for_job(
        job_id=job_id,
        job_record=job_record,
        channel=resolved_channel,
        # Subject validation only needs title/description text for guardrails.
        # Do not let this safety check make a real metadata/LLM call after the
        # script has already completed, or unattended runs can hang here.
        mock=True,
    )
    uploader = YouTubeUploader(mock=True, channel=resolved_channel)
    error = uploader.validate_script_for_generation(
        metadata=metadata_payload,
        job_dir=str(get_job_dir(job_id)),
    )
    if not error:
        return
    if os.environ.get("STOIC_BYPASS_SCRIPT_SUBJECT_VALIDATION", "").lower() in {"1", "true", "yes"}:
        return

    db.update_job(job_id, status="script_blocked", error_message=error)
    console.print()
    console.print("[bold red]Script Subject Validation Failed![/bold red]")
    console.print(f"[dim]Reason:[/dim] {error}")
    console.print("[dim]Pipeline halted before scene/TTS/images/render generation.[/dim]")
    raise typer.Exit(code=1)


@app.command("ui-dev")
def ui_dev(
    host: str = typer.Option("0.0.0.0", "--host", help="Host for both the API and Vite dev server"),
    api_port: int = typer.Option(8001, "--api-port", help="Port for the FastAPI backend"),
    frontend_port: int = typer.Option(5173, "--frontend-port", help="Port for the Vite dev server"),
) -> None:
    """Run the control UI in hot-reload development mode."""
    repo_dir = Path(__file__).parent.parent
    frontend_dir = repo_dir / "frontend"

    if not frontend_dir.exists():
        console.print("[red]Error: frontend directory not found[/red]")
        raise typer.Exit(code=1)

    npm_bin = shutil.which("npm")
    if not npm_bin:
        console.print("[red]Error: npm is required for ui-dev[/red]")
        raise typer.Exit(code=1)

    display_host = "127.0.0.1" if host == "0.0.0.0" else host
    backend_cmd = [
        sys.executable,
        "-m",
        "uvicorn",
        "src.ui_api:app",
        "--reload",
        "--host",
        host,
        "--port",
        str(api_port),
    ]
    frontend_cmd = [
        npm_bin,
        "run",
        "dev",
        "--",
        "--host",
        host,
        "--port",
        str(frontend_port),
    ]

    frontend_env = os.environ.copy()
    frontend_env["VITE_API_BASE_URL"] = f"http://{display_host}:{api_port}"

    print_header()
    console.print("[bold]Starting hot-reload UI development servers[/bold]")
    console.print(f"[dim]API:[/dim]      http://{display_host}:{api_port}")
    console.print(f"[dim]Frontend:[/dim] http://{display_host}:{frontend_port}")
    console.print("[dim]Press Ctrl+C to stop both processes.[/dim]\n")

    backend = subprocess.Popen(backend_cmd, cwd=str(repo_dir))
    frontend = subprocess.Popen(frontend_cmd, cwd=str(frontend_dir), env=frontend_env)

    try:
        while True:
            backend_code = backend.poll()
            frontend_code = frontend.poll()

            if backend_code is not None:
                _terminate_process(frontend)
                console.print(f"\n[red]Backend exited with code {backend_code}[/red]")
                raise typer.Exit(code=backend_code if backend_code is not None else 1)

            if frontend_code is not None:
                _terminate_process(backend)
                console.print(f"\n[red]Frontend exited with code {frontend_code}[/red]")
                raise typer.Exit(code=frontend_code if frontend_code is not None else 1)

            time.sleep(0.5)
    except KeyboardInterrupt:
        console.print("\n[yellow]Stopping UI development servers...[/yellow]")
        _terminate_process(frontend)
        _terminate_process(backend)
        raise typer.Exit(code=0)


@app.command()
def idea(
    count: int = typer.Option(5, "--count", "-c", help="Number of ideas to generate"),
    niche: str = typer.Option("stoicism for modern workers", "--niche", "-n", help="Content niche"),
    mock: bool = typer.Option(False, "--mock", "-m", help="Use mock data"),
) -> None:
    """Generate topic ideas for the channel."""
    print_header()
    console.print(f"[bold]Generating {count} ideas for niche:[/bold] {niche}")

    if mock or settings.mock_mode:
        console.print("[yellow]Using mock data mode[/yellow]")
        mock_ideas = [
            "How Marcus Aurelius Would Handle Your 9 AM Meeting",
            "Seneca's Advice for Dealing with Difficult Colleagues",
            "The Stoic Approach to Career Burnout",
            "Epictetus on Controlling What You Can at Work",
            "Why Modern Managers Should Read Meditations",
            "Stoic Breathing Techniques for Stressful Deadlines",
            "How to Apply Stoicism to Remote Work Challenges",
            "The Stoic Guide to Office Politics",
            "Finding Purpose: A Stoic Perspective on Your Career",
            "How to Stay Calm When Your Boss is Angry",
        ]
        console.print()
        for i, idea_text in enumerate(mock_ideas[:count], 1):
            console.print(f"[green]✓[/green] {i}. {idea_text}")
        console.print()
        console.print("[dim]Tip: Use 'python -m src.main research <your-topic>' to start a job[/dim]")
        return

    manager = LedgerStrategyManager()
    ideas_payload = manager.load_topic_plan(niche=niche)
    ideas = list(ideas_payload.get("ideas", []))[:count]
    console.print()
    for i, idea_data in enumerate(ideas, 1):
        objective = idea_data.get("objective", "balanced")
        title = idea_data.get("title", "Untitled")
        console.print(f"[green]✓[/green] {i}. [{objective}] {title}")
    console.print()
    console.print("[dim]Generated from current Milo strategy. Use 'python -m src.main research <your-topic>' to start a job[/dim]")


@app.command()
def research(
    topic: str = typer.Argument(..., help="Topic to research"),
    job_id: Optional[str] = typer.Option(None, "--job-id", help="Attach research to an existing job"),
    mock: bool = typer.Option(False, "--mock", "-m", help="Use mock data"),
    channel: Optional[Channel] = typer.Option(None, "--channel", help="Channel pipeline: stoic-modernized", show_default=False),
) -> None:
    """Perform research on a topic and store sources."""
    print_header()

    if job_id:
        job_record = _load_job_record(job_id)
    else:
        job_record = db.create_job(topic)
        job_id = job_record.job_id

    resolved_channel = _resolve_channel(channel, job_id)
    _persist_job_context(job_id, topic, resolved_channel)

    logger = JobLogger(job_id)
    db.update_job(job_id, log_path=logger.log_path)

    console.print(f"[bold]Job ID:[/bold] {job_id}")
    console.print(f"[bold]Topic:[/bold] {topic}")

    logger.info(f"Starting research for topic: {topic}")

    stage = ResearchStage(job_id=job_id, mock=mock, channel=resolved_channel)
    try:
        results = asyncio.run(stage.run(topic))
    except Exception as exc:
        error_text = str(exc)
        db.update_job(job_id, status="research_failed", error_message=error_text, log_path=logger.log_path)
        console.print()
        console.print("[bold red]Research Failed![/bold red]")
        console.print(f"[dim]Reason:[/dim] {error_text}")
        logger.info(f"Research stage failed: {error_text}")
        raise typer.Exit(code=1)
    final_topic = stage.last_topic or topic
    if final_topic != topic:
        console.print(f"[yellow]Topic replaced during research:[/yellow] {topic} -> {final_topic}")
        logger.info(f"Topic replaced during research: {topic} -> {final_topic}")
    research_path = stage.save_results(results)

    db.update_job(
        job_id,
        topic=final_topic,
        status="research_complete",
        research_path=str(research_path),
        log_path=logger.log_path,
        error_message=None,
    )
    _persist_job_context(job_id, final_topic, resolved_channel)

    console.print()
    console.print("[bold green]Research Complete![/bold green]")
    console.print(f"[dim]Job ID:[/dim] {job_id}")
    if final_topic != topic:
        console.print(f"[dim]Validated topic:[/dim] {final_topic}")
    console.print(f"[dim]Sources found:[/dim] {len(results.sources)}")
    console.print(f"[dim]Next step:[/dim] python -m src.main script {job_id}")

    logger.info("Research stage completed successfully")


@app.command()
def script(
    job_id: str = typer.Argument(..., help="Job ID from research stage"),
    mock: bool = typer.Option(False, "--mock", "-m", help="Use mock data"),
    video_mode: VideoMode = typer.Option(settings.default_video_mode, "--video-mode", help="Video mode: short or long"),
    channel: Optional[Channel] = typer.Option(None, "--channel", help="Channel pipeline override", show_default=False),
) -> None:
    """Generate a video script based on research."""
    print_header()
    job_record = _load_job_record(job_id)

    if not job_record.research_path:
        console.print("[red]Error: No research data found for this job[/red]")
        raise typer.Exit(code=1)

    research_data = load_json(Path(job_record.research_path))
    console.print(f"[bold]Generating script for:[/bold] {research_data['title']}")

    resolved_channel = _resolve_channel(channel, job_id)
    _persist_job_context(job_id, job_record.topic, resolved_channel, video_mode=video_mode)
    stage = ScriptStage(job_id=job_id, mock=mock, video_mode=video_mode, channel=resolved_channel)
    report_path = stage.script_dir / "script_generation_report.json"

    try:
        script_result = asyncio.run(stage.run(research_data))
    except ScriptGenerationError as exc:
        report = load_json(report_path) if report_path.exists() else None
        error_text = str(exc)
        db.update_job(job_id, status="script_failed", error_message=error_text)
        console.print()
        console.print("[bold red]Script Generation Failed![/bold red]")
        console.print(f"[dim]Reason:[/dim] {error_text}")
        if report:
            console.print(f"[dim]Local LLM success:[/dim] {report.get('local_llm_success')}")
            if report.get("failure_reason"):
                console.print(f"[dim]Failure reason:[/dim] {report['failure_reason']}")
            console.print(f"[dim]Inspection report:[/dim] {report_path}")
        raise typer.Exit(code=1)

    script_path = stage.save_script(script_result)
    report = load_json(report_path) if report_path.exists() else None

    db.update_job(job_id, status="script_complete", script_path=str(script_path), error_message=None)
    validated_job_record = _load_job_record(job_id)
    _validate_script_subject_before_generation(
        job_id=job_id,
        job_record=validated_job_record,
        channel=resolved_channel,
        mock=mock,
    )

    console.print()
    console.print("[bold green]Script Complete![/bold green]")
    console.print(f"[dim]Title:[/dim] {script_result.title}")
    expected_duration = "~1 minute" if video_mode == VideoMode.SHORT else "~9 minutes"
    console.print(f"[dim]Duration:[/dim] {expected_duration}")
    console.print(f"[dim]Chapters:[/dim] {len(script_result.chapters)}")
    if report:
        console.print(f"[dim]Local LLM success:[/dim] {report.get('local_llm_success')}")
        console.print(f"[dim]Script generation succeeded:[/dim] {report.get('script_generation_succeeded')}")
        console.print(f"[dim]Inspection report:[/dim] {report_path}")
    console.print(f"[dim]Next step:[/dim] python -m src.main scene {job_id}")


@app.command()
def scene(
    job_id: str = typer.Argument(..., help="Job ID from script stage"),
    mock: bool = typer.Option(False, "--mock", "-m", help="Use mock data"),
    channel: Optional[Channel] = typer.Option(None, "--channel", help="Channel pipeline override", show_default=False),
) -> None:
    """Create a scene plan for the video."""
    print_header()
    job_record = _load_job_record(job_id)

    if not job_record.script_path:
        _exit_stage_failed(job_id, "scene", "No script found for this job", "Scene Plan")

    video_mode = _resolve_video_mode(job_id=job_id)
    _validate_script_subject_before_generation(
        job_id=job_id,
        job_record=job_record,
        channel=channel,
        mock=mock,
    )
    script_data = _normalize_script_for_video_mode(load_json(Path(job_record.script_path)), video_mode)
    console.print(f"[bold]Creating scene plan for:[/bold] {script_data['title']}")

    scene_mock = mock or settings.mock_mode
    if scene_mock:
        console.print("[yellow]Using mock scene planner[/yellow]")
    else:
        console.print("[green]Using local-LLM scene planner[/green]")

    resolved_channel = _resolve_channel(channel, job_id)
    stage = SceneStage(job_id=job_id, mock=scene_mock, channel=resolved_channel)
    try:
        scene_plan = asyncio.run(stage.run(script_data))
        scene_path = stage.save_scene_plan(scene_plan)
    except Exception as exc:
        _exit_stage_failed(job_id, "scene", exc, "Scene Plan")

    db.update_job(job_id, status="scene_complete", scene_plan_path=str(scene_path), error_message=None)

    console.print()
    console.print("[bold green]Scene Plan Complete![/bold green]")
    console.print(f"[dim]Total scenes:[/dim] {len(scene_plan.scenes)}")
    console.print(f"[dim]Estimated duration:[/dim] ~{scene_plan.total_duration/60:.1f} minutes")
    console.print(f"[dim]Next step:[/dim] python -m src.main tts {job_id}")


@app.command()
def tts(
    job_id: str = typer.Argument(..., help="Job ID from scene stage"),
    provider: str = typer.Option(settings.tts_provider.value, "--provider", "-p", help="TTS provider: edge or kokoro"),
    mock: bool = typer.Option(False, "--mock", "-m", help="Use mock data"),
    channel: Optional[Channel] = typer.Option(None, "--channel", help="Channel pipeline override", show_default=False),
) -> None:
    """Generate TTS narration for the video."""
    print_header()
    job_record = _load_job_record(job_id)

    if not job_record.scene_plan_path:
        _exit_stage_failed(job_id, "tts", "No scene plan found for this job", "TTS")
    _validate_script_subject_before_generation(
        job_id=job_id,
        job_record=job_record,
        channel=channel,
        mock=mock,
    )

    scene_plan = load_json(Path(job_record.scene_plan_path))
    console.print(f"[bold]Generating TTS with provider:[/bold] {provider}")

    resolved_channel = _resolve_channel(channel, job_id)
    stage = TTSStage(job_id=job_id, provider=provider, mock=mock, channel=resolved_channel)
    try:
        audio_path = asyncio.run(stage.run(scene_plan))
        stage.save_audio_path(audio_path)
    except Exception as exc:
        _exit_stage_failed(job_id, "tts", exc, "TTS")
    db.update_job(job_id, status="tts_complete", audio_path=str(audio_path), error_message=None)

    console.print()
    console.print("[bold green]TTS Complete![/bold green]")
    console.print(f"[dim]Audio path:[/dim] {audio_path}")
    console.print(f"[dim]Scenes loaded:[/dim] {len(scene_plan.get('scenes', []))}")
    console.print(f"[dim]Next step:[/dim] python -m src.main images {job_id}")


@app.command()
def music(
    job_id: str = typer.Argument(..., help="Job ID after TTS stage"),
    query: Optional[str] = typer.Option(None, "--query", help="Override Pixabay search query"),
) -> None:
    """Download royalty-free background music for the video."""
    print_header()
    job_record = _load_job_record(job_id)

    stage = BackgroundMusicStage(job_id=job_id)
    try:
        music_path = asyncio.run(stage.run(topic=job_record.topic, audio_path=job_record.audio_path, query=query))
    except Exception as exc:
        _exit_stage_failed(job_id, "music", exc, "Background Music")

    db.update_job(job_id, status="music_complete", error_message=None)

    console.print()
    console.print("[bold green]Background Music Complete![/bold green]")
    console.print(f"[dim]Music path:[/dim] {music_path}")
    console.print(f"[dim]Metadata path:[/dim] {stage.metadata_path}")
    console.print(f"[dim]Next step:[/dim] python -m src.main images {job_id}")


@app.command()
def images(
    job_id: str = typer.Argument(..., help="Job ID from tts stage"),
    mock: bool = typer.Option(False, "--mock", "-m", help="Use mock data"),
    placeholder_only: bool = typer.Option(False, "--placeholder-images", help="Skip sd-cli and generate local placeholder scene cards"),
    allow_placeholder_images: bool = typer.Option(
        False,
        "--allow-placeholder-images",
        help="Explicitly allow placeholder scene cards for a real run after Rafael requests them.",
    ),
    channel: Optional[Channel] = typer.Option(None, "--channel", help="Channel pipeline override", show_default=False),
) -> None:
    """Generate images for each scene."""
    print_header()
    job_record = _load_job_record(job_id)

    if not job_record.scene_plan_path:
        console.print("[red]Error: No scene plan found for this job[/red]")
        raise typer.Exit(code=1)
    _validate_script_subject_before_generation(
        job_id=job_id,
        job_record=job_record,
        channel=channel,
        mock=mock,
    )

    scene_plan = load_json(Path(job_record.scene_plan_path))
    console.print(f"[bold]Generating {len(scene_plan['scenes'])} images for scenes...[/bold]")

    stage = ImageGenerationStage(
        job_id=job_id,
        mock=mock,
        placeholder_only=placeholder_only,
        allow_placeholder_override=allow_placeholder_images,
    )
    try:
        assets = asyncio.run(stage.run(scene_plan))
    except ImageGenerationError as exc:
        error_text = str(exc)
        db.update_job(job_id, status="images_failed", error_message=error_text)
        console.print()
        console.print("[bold red]Image Generation Failed![/bold red]")
        console.print(f"[dim]Reason:[/dim] {error_text}")
        raise typer.Exit(code=1)

    assets_path = stage.save_assets(assets)

    db.update_job(job_id, status="images_complete", images_dir=str(stage.images_dir), error_message=None)

    console.print()
    console.print("[bold green]Image Generation Complete![/bold green]")
    console.print(f"[dim]Images generated:[/dim] {len(assets)}")
    console.print(f"[dim]Assets manifest:[/dim] {assets_path}")
    console.print(f"[dim]Next step:[/dim] python -m src.main subtitles {job_id}")


@app.command()
def subtitles(
    job_id: str = typer.Argument(..., help="Job ID from images stage"),
    mock: bool = typer.Option(False, "--mock", "-m", help="Use mock data"),
) -> None:
    """Generate subtitles for the video."""
    print_header()
    job_record = _load_job_record(job_id)

    if not job_record.script_path:
        _exit_stage_failed(job_id, "subtitles", "No script found for this job", "Subtitles")

    _validate_script_subject_before_generation(
        job_id=job_id,
        job_record=job_record,
        channel=None,
        mock=mock,
    )
    video_mode = _resolve_video_mode(job_id=job_id)
    script_data = _normalize_script_for_video_mode(load_json(Path(job_record.script_path)), video_mode)
    stage = SubtitleStage(job_id=job_id, mock=mock)
    try:
        result = asyncio.run(stage.run(script_data, job_record.audio_path))
        stage.save_subtitles(result)
    except Exception as exc:
        _exit_stage_failed(job_id, "subtitles", exc, "Subtitles")

    db.update_job(job_id, status="subtitles_complete", subtitle_path=result.srt_path, error_message=None)

    console.print()
    console.print("[bold green]Subtitles Complete![/bold green]")
    console.print(f"[dim]Segments:[/dim] {len(result.segments)}")
    console.print(f"[dim]Next step:[/dim] python -m src.main render {job_id}")


@app.command()
def render(
    job_id: str = typer.Argument(..., help="Job ID from subtitles stage"),
    mock: bool = typer.Option(False, "--mock", "-m", help="Use mock data"),
    video_mode: Optional[VideoMode] = typer.Option(None, "--video-mode", help="Video mode: short or long"),
    renderer_type: str = typer.Option(
        "remotion", "--renderer", "-r",
        help="Renderer to use: remotion or ffmpeg"
    ),
    platform: Optional[RemotionPlatform] = typer.Option(
        None,
        "--platform",
        help="Remotion platform preset: youtube or tiktok. Defaults from video mode if omitted.",
    ),
    channel: Optional[Channel] = typer.Option(None, "--channel", help="Channel pipeline override", show_default=False),
) -> None:
    """Render the final video with ffmpeg or Remotion."""
    print_header()
    job_record = _load_job_record(job_id)

    if not job_record.scene_plan_path:
        _exit_stage_failed(job_id, "render", "No scene plan found. Run scene stage first.", "Render")
    if not job_record.audio_path:
        _exit_stage_failed(job_id, "render", "No audio file found. Run TTS stage first.", "Render")
    _validate_script_subject_before_generation(
        job_id=job_id,
        job_record=job_record,
        channel=channel,
        mock=mock,
    )

    audio_vtt_path = get_job_dir(job_id) / "audio" / "narration.vtt"
    subtitle_json_path = get_job_dir(job_id) / "subtitles" / "subtitles.json"
    should_refresh_subtitles = (
        audio_vtt_path.exists()
        and (
            not job_record.subtitle_path
            or not subtitle_json_path.exists()
            or audio_vtt_path.stat().st_mtime > subtitle_json_path.stat().st_mtime
        )
    )
    if should_refresh_subtitles:
        console.print("[cyan]Refreshing subtitles from Edge TTS VTT before render...[/cyan]")
        subtitle_video_mode = _resolve_video_mode(job_id=job_id)
        subtitle_script_data = _normalize_script_for_video_mode(load_json(Path(job_record.script_path)), subtitle_video_mode)
        subtitle_stage = SubtitleStage(job_id=job_id, mock=mock)
        try:
            subtitle_result = asyncio.run(subtitle_stage.run(subtitle_script_data, job_record.audio_path))
            subtitle_stage.save_subtitles(subtitle_result)
        except Exception as exc:
            _exit_stage_failed(job_id, "render", exc, "Render")
        db.update_job(job_id, status="subtitles_complete", subtitle_path=subtitle_result.srt_path)
        job_record = _load_job_record(job_id)

    if not job_record.subtitle_path:
        _exit_stage_failed(job_id, "render", "No subtitles found. Run subtitles stage first.", "Render")

    resolved_video_mode = _resolve_video_mode(video_mode=video_mode, job_id=job_id)

    width = settings.short_video_width if resolved_video_mode == VideoMode.SHORT else settings.video_width
    height = settings.short_video_height if resolved_video_mode == VideoMode.SHORT else settings.video_height

    background_music_path: Optional[Path] = None
    if settings.background_music_enabled:
        background_stage = BackgroundMusicStage(job_id=job_id)
        try:
            existing_track = None
            for pattern in ("background_music.mp3", "background_music.wav", "background_music.ogg", "background_music.m4a"):
                candidate = background_stage.audio_dir / pattern
                if candidate.exists():
                    existing_track = candidate
                    break
            if existing_track is not None:
                background_music_path = existing_track
            else:
                background_music_path = asyncio.run(
                    background_stage.run(topic=job_record.topic, audio_path=job_record.audio_path)
                )
        except Exception as exc:
            console.print(f"[yellow]Warning: Background music skipped: {exc}[/yellow]")

    resolved_channel = _resolve_channel(channel, job_id)

    if renderer_type == "remotion":
        mode = "portrait" if resolved_video_mode == VideoMode.SHORT else "landscape"
        resolved_platform = platform.value if platform else _default_remotion_platform(mode, resolved_channel)
        console.print(f"[bold cyan]Using Remotion renderer ({mode}, platform={resolved_platform})[/bold cyan]")
        renderer = RemotionRenderer(
            job_id=job_id,
            frontend_dir=settings.project_root / "frontend",
            width=width,
            height=height,
            fps=settings.video_fps,
            mode=mode,
            platform=resolved_platform,
            channel=resolved_channel,
        )
        try:
            result = renderer.run()
            output_path = result['video_path']
        except Exception as exc:
            _exit_stage_failed(job_id, "render", exc, "Render")
    else:
        try:
            scenes_data = load_json(Path(job_record.scene_plan_path)).get("scenes", [])
            scenes = [Scene(**scene) for scene in scenes_data]

            renderer = VideoRenderer(job_id=job_id, mock=mock)
            output_path = renderer.output_dir / "final.mp4"
            config = VideoRenderConfig(
                scenes=scenes,
                audio_path=job_record.audio_path,
                background_music_path=str(background_music_path) if background_music_path else None,
                subtitle_path=job_record.subtitle_path,
                output_path=str(output_path),
                width=width,
                height=height,
            )
            result = asyncio.run(renderer.run(config))
        except Exception as exc:
            _exit_stage_failed(job_id, "render", exc, "Render")

    render_manifest_path = get_job_dir(job_id) / "render_manifest.json"
    try:
        save_json(
            {
                "renderer": renderer_type,
                "video_mode": resolved_video_mode.value,
                "video_path": result['video_path'] if isinstance(result, dict) else result.video_path,
                "background_music_included": bool(background_music_path),
                "background_music_path": str(background_music_path) if background_music_path else None,
                "rendered_at": datetime.now(UTC).isoformat(),
            },
            render_manifest_path,
        )

        db.update_job(
            job_id,
            status="render_complete",
            video_path=result['video_path'] if isinstance(result, dict) else result.video_path,
            error_message=None,
        )
    except Exception as exc:
        _exit_stage_failed(job_id, "render", exc, "Render")

    console.print()
    console.print("[bold green]Rendering Complete![/bold green]")
    console.print(f"[dim]Video path:[/dim] {result['video_path'] if isinstance(result, dict) else result.video_path}")
    console.print(f"[dim]Renderer:[/dim] {renderer_type}")
    console.print(f"[dim]Mode:[/dim] {resolved_video_mode.value}")
    console.print(f"[dim]Next step:[/dim] python -m src.main metadata {job_id}")


@app.command()
def metadata(
    job_id: str = typer.Argument(..., help="Job ID from render stage"),
    mock: bool = typer.Option(False, "--mock", "-m", help="Use mock data"),
    channel: Optional[Channel] = typer.Option(None, "--channel", help="Channel pipeline override", show_default=False),
) -> None:
    """Generate YouTube metadata (title, description, tags, chapters)."""
    print_header()
    job_record = _load_job_record(job_id)

    if not job_record.script_path:
        _exit_stage_failed(job_id, "metadata", "No script found for this job", "Metadata")

    try:
        metadata_payload = _generate_metadata_payload_for_job(
            job_id=job_id,
            job_record=job_record,
            channel=channel,
            mock=mock,
        )
        metadata_path = _save_metadata(job_id, metadata_payload)
        covered_news_added = _save_covered_news(job_id, metadata_payload["title"])
        media_explorer_result = None
        video_path = getattr(job_record, "video_path", None)
        if video_path:
            media_explorer_result = publish_media_explorer_artifacts(job_id, video_path, metadata_payload)
        else:
            console.print("[yellow]Warning: No rendered video path found; media explorer publish skipped.[/yellow]")
        db.update_job(job_id, status="metadata_complete", metadata_path=str(metadata_path), error_message=None)
    except Exception as exc:
        _exit_stage_failed(job_id, "metadata", exc, "Metadata")

    console.print()
    console.print("[bold green]Metadata Complete![/bold green]")
    console.print(f"[dim]Title:[/dim] {metadata_payload['title']}")
    console.print(f"[dim]Tags:[/dim] {len(metadata_payload['tags'])}")
    console.print(f"[dim]Metadata path:[/dim] {metadata_path}")
    if covered_news_added:
        console.print(f"[dim]Covered stories saved:[/dim] {covered_news_added}")
    if media_explorer_result:
        console.print(f"[dim]Media explorer page:[/dim] {media_explorer_result['path']}")
        if media_explorer_result.get("url"):
            console.print(f"[dim]Public media page:[/dim] {media_explorer_result['url']}")
    console.print(f"[dim]Next step:[/dim] python -m src.main upload {job_id}")


def _format_tiktok_hashtag(tag: str) -> str | None:
    words = re.findall(r'[A-Za-z0-9]+', str(tag))
    if not words:
        return None
    stopwords = {'at', 'the', 'a', 'an', 'and', 'or', 'to', 'of', 'for', 'your', 'you', 'what'}
    kept = [word for word in words if word.lower() not in stopwords]
    if not kept:
        kept = words
    slug = '#' + ''.join(word[:1].upper() + word[1:] for word in kept[:4])
    if len(slug) <= 2:
        return None
    return slug[:28].rstrip()


def _build_tiktok_share_copy(metadata_payload: dict, channel_name: str) -> tuple[str, str]:
    raw_title = str(metadata_payload.get('title') or 'Untitled Video').replace(f' | {channel_name}', '').strip()
    raw_description = str(metadata_payload.get('description') or '').strip()
    body = raw_description.split('\n\nResources:', 1)[0].strip()
    tags = metadata_payload.get('tags') if isinstance(metadata_payload.get('tags'), list) else []
    generic_tags = {'stoicism', 'stoic philosophy', 'modern stoicism', 'stoic modernized'}
    prioritized_tags = [tag for tag in tags if str(tag).strip().lower() not in generic_tags]
    hashtags = []
    seen: set[str] = set()
    for base in ['Stoicism', 'StoicModernized', *prioritized_tags, *tags]:
        slug = _format_tiktok_hashtag(base)
        if not slug:
            continue
        lowered = slug.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        hashtags.append(slug)
        if len(hashtags) >= 4:
            break

    if not hashtags:
        hashtags = re.findall(r'#[A-Za-z0-9_]+', body)

    normalized_hashtags = []
    seen_normalized: set[str] = set()
    for tag in hashtags:
        slug = _format_tiktok_hashtag(tag)
        if not slug:
            continue
        lowered = slug.lower()
        if lowered in seen_normalized:
            continue
        seen_normalized.add(lowered)
        normalized_hashtags.append(slug)
        if len(normalized_hashtags) >= 4:
            break

    body = re.sub(r'Subscribe to @stoic-modernized[^.#!?]*(?:[.!?]|$)', '', body, flags=re.IGNORECASE).strip()
    body = re.sub(r'#[A-Za-z0-9_]+', '', body).strip()
    body = re.sub(r'\s+', ' ', body).strip(' -')
    sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', body) if s.strip()]
    short_body = ' '.join(sentences[:2]).strip() or body or raw_title
    if len(short_body) > 180:
        short_body = short_body[:177].rsplit(' ', 1)[0].rstrip(' ,;:-') + '...'
    tiktok_description = short_body
    if normalized_hashtags:
        tiktok_description = f"{short_body} {' '.join(normalized_hashtags)}".strip()
    return raw_title, tiktok_description


def _send_telegram_upload(job_id: str, video_url: str, title: str, metadata_payload: Optional[dict] = None) -> None:
    """Send upload notification to Telegram."""
    try:
        # Get bot token from .env
        env_path = Path(__file__).parent.parent / '.env'
        token = None
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                if line.startswith('TELEGRAM_BOT_TOKEN='):
                    token = line.split('=', 1)[1].strip()
                    break
        if not token:
            console.print("[yellow]⚠ No TELEGRAM_BOT_TOKEN found, skipping Telegram send[/yellow]")
            return

        # Get recipient
        recipient_id = os.environ.get('TELEGRAM_CHAT_ID', '508227795')

        context = _load_job_context(job_id)
        channel_name = context.get('channel_name', settings.channel_name)
        clean_title = title.replace(f' | {channel_name}', '').strip()
        tiktok_title, tiktok_description = _build_tiktok_share_copy(metadata_payload or {'title': clean_title}, channel_name)
        caption = (
            f"🎬 New video uploaded!\n"
            f"\n"
            f"\"{clean_title}\" — {channel_name}\n"
            f"\n"
            f"<a href=\"{video_url}\">Watch on YouTube</a>\n"
            f"\n"
            f"TikTok title: {tiktok_title}\n"
            f"TikTok description: {tiktok_description}"
        )

        import urllib.parse
        import urllib.request
        url = f'https://api.telegram.org/bot{token}/sendMessage'
        params = urllib.parse.urlencode({
            'chat_id': recipient_id,
            'text': caption,
            'parse_mode': 'HTML',
        }).encode()
        req = urllib.request.Request(url, data=params, method='POST')
        urllib.request.urlopen(req, timeout=15)
        console.print("[green]✓ Sent to Telegram[/green]")
    except Exception as e:
        console.print(f"[yellow]⚠ Telegram send failed: {e}[/yellow]")


@app.command()
def upload(
    job_id: str = typer.Argument(..., help="Job ID from metadata stage"),
    mock: bool = typer.Option(False, "--mock", "-m", help="Use mock data"),
    video_path: Optional[str] = typer.Option(None, "--video-path", help="Override the video file to upload"),
    channel: Optional[Channel] = typer.Option(None, "--channel", help="Channel pipeline override", show_default=False),
) -> None:
    """Upload video to YouTube."""
    print_header()
    job_record = _load_job_record(job_id)

    resolved_video_path = video_path or job_record.video_path

    if not resolved_video_path:
        console.print("[red]Error: No video found. Run render stage first.[/red]")
        raise typer.Exit(code=1)
    if not Path(resolved_video_path).exists():
        console.print(f"[red]Error: Video file not found:[/red] {resolved_video_path}")
        raise typer.Exit(code=1)
    if not job_record.metadata_path:
        console.print("[red]Error: No metadata found. Run metadata stage first.[/red]")
        raise typer.Exit(code=1)

    # Check if OAuth2 is configured when not in mock mode
    if not mock and not settings.youtube_api_key:
        console.print("[yellow]⚠ YouTube API key not configured[/yellow]")
        console.print("[yellow]⚠ OAuth2 credentials not found[/yellow]")
        console.print("\n[bold]To enable YouTube uploads:[/bold]")
        console.print("  1. Run: python -m src.auth_oauth")
        console.print("  2. Follow the browser authentication flow")
        console.print("\n[bold]Or use mock mode for testing:[/bold]")
        console.print("  python -m src.main upload --mock <job_id>")
        console.print()
        raise typer.Exit(code=1)

    metadata_payload = _generate_metadata_payload_for_job(
        job_id=job_id,
        job_record=job_record,
        channel=channel,
        mock=mock,
    )
    _save_metadata(job_id, metadata_payload)
    resolved_channel = _resolve_channel(channel, job_id)
    uploader = YouTubeUploader(mock=mock, channel=resolved_channel)
    result = asyncio.run(
        uploader.upload(
            video_path=resolved_video_path,
            metadata=metadata_payload,
            thumbnail_path=job_record.thumbnail_path,
            job_dir=str(settings.jobs_dir / job_id),
        )
    )

    status_value = "completed" if result.upload_status == "completed" else result.upload_status
    db.update_job(job_id, status=status_value, video_url=result.video_url)

    console.print()
    if result.upload_status == "completed":
        console.print("[bold green]✓ Upload Complete![/bold green]")
        console.print(f"[dim]Video URL:[/dim] {result.video_url}")
        console.print(f"\n[dim]To view your video:[/dim] {result.video_url}")
    else:
        console.print("[bold yellow]✗ Upload not completed.[/bold yellow]")
        if result.error:
            console.print(f"[dim]Reason:[/dim] {result.error}")
            if "oauth" in result.error.lower() or "token" in result.error.lower():
                console.print("\n[dim]Run: python -m src.auth_oauth to re-authenticate[/dim]")
    console.print(f"[dim]Job ID:[/dim] {job_id}")
    console.print(f"[dim]Uploaded file:[/dim] {resolved_video_path}")

    # Auto-send to Telegram on successful real upload
    if result.upload_status == 'completed' and not mock:
        _send_telegram_upload(job_id, result.video_url, metadata_payload.get('title', ''), metadata_payload)


@app.command()
def distribute(
    job_id: str = typer.Argument(..., help="Job ID from metadata/upload stage"),
    mock: bool = typer.Option(False, "--mock", "-m", help="Write a dry-run social distribution manifest without external API calls"),
    platforms: str = typer.Option(settings.social_distribution_platforms, "--platforms", help="Comma-separated platforms: instagram,facebook,tiktok"),
) -> None:
    """Distribute rendered video to TikTok, Instagram Reels, and Facebook Reels."""
    print_header()
    _load_job_record(job_id)
    selected_platforms = [item.strip().lower() for item in platforms.split(",") if item.strip()]
    stage = SocialDistributionStage(job_id=job_id, mock=mock, platforms=selected_platforms)
    result = stage.run()
    manifest_path = settings.jobs_dir / job_id / "distribution" / "social_uploads.json"

    status_value = "social_distributed" if result["status"] in {"completed", "mock_completed"} else result["status"]
    db.update_job(job_id, status=status_value)

    console.print()
    if result["status"] in {"completed", "mock_completed"}:
        console.print("[bold green]✓ Social Distribution Complete![/bold green]")
    else:
        console.print("[bold yellow]Social Distribution needs attention.[/bold yellow]")
    console.print(f"[dim]Status:[/dim] {result['status']}")
    console.print(f"[dim]Manifest:[/dim] {manifest_path}")
    for platform in result.get("platforms", []):
        line = f"{platform.get('platform')}: {platform.get('status')}"
        if platform.get("url"):
            line += f" ({platform['url']})"
        if platform.get("error"):
            line += f" — {platform['error']}"
        console.print(f"[dim]{line}[/dim]")


@app.command()
def run(
    topic: str = typer.Argument(..., help="Topic for the video"),
    mock: bool = typer.Option(False, "--mock", "-m", help="Use mock data for all stages"),
    provider: str = typer.Option(settings.tts_provider.value, "--provider", "-p", help="TTS provider: edge or kokoro"),
    skip_upload: bool = typer.Option(False, "--skip-upload", help="Run the full pipeline but skip the upload stage"),
    distribute_social: bool = typer.Option(False, "--distribute-social", help="After upload, distribute to configured TikTok/Instagram/Facebook destinations"),
    social_mock: bool = typer.Option(False, "--social-mock", help="Dry-run social distribution even when the main pipeline is real"),
    video_mode: VideoMode = typer.Option(settings.default_video_mode, "--video-mode", help="Video mode: short or long"),
    renderer: str = typer.Option("remotion", "--renderer", "-r", help="Renderer to use: remotion, ffmpeg, or both"),
    placeholder_images: bool = typer.Option(False, "--placeholder-images", help="Skip sd-cli and generate local placeholder scene cards"),
    allow_placeholder_images: bool = typer.Option(
        False,
        "--allow-placeholder-images",
        help="Explicitly allow placeholder scene cards for a real run after Rafael requests them.",
    ),
    platform: Optional[RemotionPlatform] = typer.Option(
        None,
        "--platform",
        help="Remotion platform preset for the render stage: youtube or tiktok.",
    ),
) -> None:
    """Run the complete pipeline for a topic."""
    job_record = db.create_job(topic)
    job_id = job_record.job_id
    _persist_job_context(job_id, topic, settings.default_channel, video_mode=video_mode)

    with job_output_capture(job_id):
        print_header()
        console.print(f"[bold]Running complete pipeline for:[/bold] {topic}")
        if skip_upload:
            console.print("[yellow]Upload stage will be skipped[/yellow]")
        if placeholder_images:
            if not (mock or settings.mock_mode or allow_placeholder_images):
                console.print("[bold red]Placeholder scene cards are blocked for real Stoic daily runs.[/bold red]")
                console.print("[dim]Daily jobs must use real generated images. Only rerun with placeholders after Rafael explicitly requests them.[/dim]")
                raise typer.Exit(code=1)
            console.print("[yellow]Using placeholder scene cards instead of sd-cli[/yellow]")

        research_stage_mock = mock or settings.mock_mode
        script_stage_mock = mock or settings.mock_mode
        scene_stage_mock = mock or settings.mock_mode
        media_stage_mock = mock or settings.mock_mode

        if not mock and not settings.mock_mode:
            console.print(
                f"[green]Using hybrid local mode: real research + real script + real scene planner + real local media generation ({video_mode.value})[/green]"
            )
            research_stage_mock = False
            script_stage_mock = False
            scene_stage_mock = False
            media_stage_mock = False
        else:
            console.print("[yellow]Using mock mode for local-friendly generation[/yellow]")

        console.print(f"[bold]Job ID:[/bold] {job_id}")
        console.print()

        research(topic=topic, job_id=job_id, mock=research_stage_mock)
        script(job_id=job_id, mock=script_stage_mock, video_mode=video_mode)
        
        # Quality gate: Run Mittens script review before render
        console.print()
        console.print("[bold cyan]Running quality gate (Mittens)...[/bold cyan]")
        try:
            quality_gate = QualityGateStage(job_id=job_id)
            quality_result = quality_gate.run()
            console.print()
            console.print("[bold green]✓ Quality gate passed![/bold green]")
            console.print(f"[dim]Title:[/dim] {quality_result['title']}")
            console.print(f"[dim]Issues found:[/dim] {len(quality_result['issues'])}")
            console.print(f"[dim]Report:[/dim] {quality_result['report_path']}")
        except QualityGateError as e:
            console.print()
            console.print("[bold red]✗ Quality gate failed![/bold red]")
            console.print(f"[dim]Reason:[/dim] {e}")
            console.print()
            console.print("[bold]Pipeline halted. Fix issues and retry:[/bold]")
            console.print(f"[dim]python -m src.main retry {job_id} --stage script[/dim]")
            raise typer.Exit(code=1)
        
        scene(job_id=job_id, mock=scene_stage_mock)
        tts(job_id=job_id, provider=provider, mock=media_stage_mock)
        if settings.background_music_enabled:
            try:
                music(job_id=job_id)
            except Exception as exc:
                console.print(f"[yellow]Background music skipped: {exc}[/yellow]")
        # Generate subtitles before images. Subtitle generation retimes scenes
        # from the real narration VTT/audio; images must be planned from that
        # final scene timing instead of the scene stage's pre-TTS estimates.
        subtitles(job_id=job_id, mock=media_stage_mock)
        images(
            job_id=job_id,
            mock=media_stage_mock,
            placeholder_only=placeholder_images,
            allow_placeholder_images=allow_placeholder_images,
        )

        # Render stage - supports ffmpeg, remotion, or both
        renderers_to_run = [renderer] if renderer != "both" else ["remotion", "ffmpeg"]
        for r in renderers_to_run:
            console.print(f"[bold cyan]Rendering with {r}...[/bold cyan]")
            render(job_id=job_id, mock=media_stage_mock, video_mode=video_mode, renderer_type=r, platform=platform)
            console.print(f"[dim]Render ({r}) complete.[/dim]")

        metadata(job_id=job_id, mock=script_stage_mock)

        if not skip_upload:
            upload(job_id=job_id, mock=mock, video_path=None)
        else:
            db.update_job(job_id, status="ready_for_upload")

        if distribute_social:
            distribute(job_id=job_id, mock=(social_mock or mock), platforms=settings.social_distribution_platforms)

        console.print()
        console.print("[bold green]Pipeline Complete![/bold green]")
        console.print(f"[dim]Job ID:[/dim] {job_id}")
        console.print(f"[dim]Output directory:[/dim] {settings.jobs_dir / job_id}")
        console.print()
        console.print("[dim]To view job details:[/dim] python -m src.main jobs")


@app.command()
def jobs(
    status: Optional[str] = typer.Option(None, "--status", "-s", help="Filter by status"),
) -> None:
    """List all pipeline jobs."""
    print_header()
    jobs_list = db.get_all_jobs(status)
    if not jobs_list:
        console.print("[dim]No jobs found.[/dim]")
        return
    print_job_table(jobs_list)


@app.command()
def retry(
    job_id: str = typer.Argument(..., help="Job ID to retry"),
    stage: Optional[str] = typer.Option(None, "--stage", "-s", help="Specific stage to retry"),
    mock: bool = typer.Option(False, "--mock", "-m", help="Use mock data"),
    video_mode: VideoMode = typer.Option(settings.default_video_mode, "--video-mode", help="Video mode: short or long"),
    channel: Optional[Channel] = typer.Option(None, "--channel", help="Channel override", show_default=False),
) -> None:
    """Retry a failed stage for a job."""
    print_header()
    job_record = _load_job_record(job_id)

    console.print(f"[bold]Retrying job:[/bold] {job_id}")
    console.print(f"[bold]Current status:[/bold] {job_record.status}")

    if stage:
        console.print(f"[bold]Retrying stage:[/bold] {stage}")
        stage_map = {
            "research": lambda: research(topic=job_record.topic, job_id=job_id, mock=mock),
            "script": lambda: script(job_id=job_id, mock=mock, video_mode=video_mode, channel=_resolve_channel(channel, job_id)),
            "scene": lambda: scene(job_id=job_id, mock=mock, channel=_resolve_channel(None, job_id)),
            "tts": lambda: tts(job_id=job_id, provider=settings.tts_provider.value, mock=mock, channel=_resolve_channel(None, job_id)),
            "music": lambda: music(job_id=job_id),
            "images": lambda: images(job_id=job_id, mock=mock, channel=_resolve_channel(None, job_id)),
            "subtitles": lambda: subtitles(job_id=job_id, mock=mock),
            "render": lambda: render(job_id=job_id, mock=mock),
            "metadata": lambda: metadata(job_id=job_id, mock=mock),
            "upload": lambda: upload(job_id=job_id, mock=mock),
            "distribute": lambda: distribute(job_id=job_id, mock=mock),
        }
        runner = stage_map.get(stage)
        if not runner:
            console.print(f"[red]Unknown stage:[/red] {stage}")
            raise typer.Exit(code=1)
        runner()
    else:
        run(topic=job_record.topic, mock=mock, provider=settings.tts_provider.value, skip_upload=False)


@app.command()
def status(
    job_id: str = typer.Argument(..., help="Job ID to check"),
) -> None:
    """Check the status of a specific job."""
    print_header()
    job_record = _load_job_record(job_id)

    table = Table(title=f"Job Status: {job_record.job_id[:8]}...")
    table.add_column("Field", style="cyan")
    table.add_column("Value", style="white")

    table.add_row("Topic", job_record.topic)
    table.add_row("Status", job_record.status)
    table.add_row("Created", job_record.created_at.strftime("%Y-%m-%d %H:%M:%S"))

    if job_record.started_at:
        table.add_row("Started", job_record.started_at.strftime("%Y-%m-%d %H:%M:%S"))
    if job_record.completed_at:
        table.add_row("Completed", job_record.completed_at.strftime("%Y-%m-%d %H:%M:%S"))
    if job_record.error_message:
        table.add_row("Error", job_record.error_message)
    if job_record.video_path:
        table.add_row("Video", job_record.video_path)
    if job_record.metadata_path:
        table.add_row("Metadata", job_record.metadata_path)
    if job_record.log_path:
        table.add_row("Log", job_record.log_path)

    console.print(table)


if __name__ == "__main__":
    app()
