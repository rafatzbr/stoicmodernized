"""Main CLI entry point for stoic-modernized."""

import asyncio
import contextlib
import io
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from src.config import VideoMode, settings
from src.database import db
from src.logging_config import JobLogger
from src.models import Scene, VideoRenderConfig
from src.stages.images import ImageGenerationError, ImageGenerationStage
from src.stages.render import VideoRenderer
from src.stages.research import ResearchStage
from src.stages.scenes import SceneStage
from src.stages.script import ScriptGenerationError, ScriptStage
from src.stages.subtitles import SubtitleStage
from src.stages.tts import TTSStage
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


def _load_job_record(job_id: str):
    job_record = db.get_job(job_id)
    if not job_record:
        console.print(f"[red]Error: Job {job_id} not found[/red]")
        raise typer.Exit(code=1)
    return job_record


def _save_metadata(job_id: str, metadata_payload: dict) -> Path:
    metadata_dir = get_job_dir(job_id) / "metadata"
    metadata_dir.mkdir(parents=True, exist_ok=True)
    metadata_path = metadata_dir / "metadata.json"
    save_json(metadata_payload, metadata_path)
    db.update_job(job_id, status="metadata_complete", metadata_path=str(metadata_path))
    return metadata_path


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

    console.print("[yellow]Real idea generation not yet implemented.[/yellow]")
    console.print("[dim]Please use --mock flag for demo purposes[/dim]")


@app.command()
def research(
    topic: str = typer.Argument(..., help="Topic to research"),
    job_id: Optional[str] = typer.Option(None, "--job-id", help="Attach research to an existing job"),
    mock: bool = typer.Option(False, "--mock", "-m", help="Use mock data"),
) -> None:
    """Perform research on a topic and store sources."""
    print_header()

    if job_id:
        job_record = _load_job_record(job_id)
    else:
        job_record = db.create_job(topic)
        job_id = job_record.job_id

    logger = JobLogger(job_id)
    db.update_job(job_id, log_path=logger.log_path)

    console.print(f"[bold]Job ID:[/bold] {job_id}")
    console.print(f"[bold]Topic:[/bold] {topic}")

    logger.info(f"Starting research for topic: {topic}")

    stage = ResearchStage(job_id=job_id, mock=mock)
    results = asyncio.run(stage.run(topic))
    research_path = stage.save_results(results)

    db.update_job(job_id, status="research_complete", research_path=str(research_path), log_path=logger.log_path)

    console.print()
    console.print("[bold green]Research Complete![/bold green]")
    console.print(f"[dim]Job ID:[/dim] {job_id}")
    console.print(f"[dim]Sources found:[/dim] {len(results.sources)}")
    console.print(f"[dim]Next step:[/dim] python -m src.main script {job_id}")

    logger.info("Research stage completed successfully")


@app.command()
def script(
    job_id: str = typer.Argument(..., help="Job ID from research stage"),
    mock: bool = typer.Option(False, "--mock", "-m", help="Use mock data"),
    video_mode: VideoMode = typer.Option(VideoMode.LONG, "--video-mode", help="Video mode: short or long"),
) -> None:
    """Generate a video script based on research."""
    print_header()
    job_record = _load_job_record(job_id)

    if not job_record.research_path:
        console.print("[red]Error: No research data found for this job[/red]")
        raise typer.Exit(code=1)

    research_data = load_json(Path(job_record.research_path))
    console.print(f"[bold]Generating script for:[/bold] {research_data['title']}")

    stage = ScriptStage(job_id=job_id, mock=mock, video_mode=video_mode)
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

    console.print()
    console.print("[bold green]Script Complete![/bold green]")
    console.print(f"[dim]Title:[/dim] {script_result.title}")
    console.print(f"[dim]Duration:[/dim] ~9 minutes")
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
) -> None:
    """Create a scene plan for the video."""
    print_header()
    job_record = _load_job_record(job_id)

    if not job_record.script_path:
        console.print("[red]Error: No script found for this job[/red]")
        raise typer.Exit(code=1)

    script_data = load_json(Path(job_record.script_path))
    console.print(f"[bold]Creating scene plan for:[/bold] {script_data['title']}")

    scene_mock = mock
    if not scene_mock and not settings.mock_mode:
        scene_mock = True
        console.print("[yellow]Using mock scene planner in hybrid local mode[/yellow]")

    stage = SceneStage(job_id=job_id, mock=scene_mock)
    scene_plan = asyncio.run(stage.run(script_data))
    scene_path = stage.save_scene_plan(scene_plan)

    db.update_job(job_id, status="scene_complete", scene_plan_path=str(scene_path))

    console.print()
    console.print("[bold green]Scene Plan Complete![/bold green]")
    console.print(f"[dim]Total scenes:[/dim] {len(scene_plan.scenes)}")
    console.print(f"[dim]Estimated duration:[/dim] ~{scene_plan.total_duration/60:.1f} minutes")
    console.print(f"[dim]Next step:[/dim] python -m src.main tts {job_id}")


@app.command()
def tts(
    job_id: str = typer.Argument(..., help="Job ID from scene stage"),
    provider: str = typer.Option("local", "--provider", "-p", help="TTS provider (local, edge, or elevenlabs)"),
    mock: bool = typer.Option(False, "--mock", "-m", help="Use mock data"),
) -> None:
    """Generate TTS narration for the video."""
    print_header()
    job_record = _load_job_record(job_id)

    if not job_record.scene_plan_path:
        console.print("[red]Error: No scene plan found for this job[/red]")
        raise typer.Exit(code=1)

    scene_plan = load_json(Path(job_record.scene_plan_path))
    console.print(f"[bold]Generating TTS with provider:[/bold] {provider}")

    stage = TTSStage(job_id=job_id, provider=provider, mock=mock)
    audio_path = asyncio.run(stage.run(scene_plan))
    stage.save_audio_path(audio_path)

    console.print()
    console.print("[bold green]TTS Complete![/bold green]")
    console.print(f"[dim]Audio path:[/dim] {audio_path}")
    console.print(f"[dim]Scenes loaded:[/dim] {len(scene_plan.get('scenes', []))}")
    console.print(f"[dim]Next step:[/dim] python -m src.main images {job_id}")


@app.command()
def images(
    job_id: str = typer.Argument(..., help="Job ID from tts stage"),
    mock: bool = typer.Option(False, "--mock", "-m", help="Use mock data"),
    placeholder_only: bool = typer.Option(False, "--placeholder-images", help="Skip sd-cli and generate local placeholder scene cards"),
) -> None:
    """Generate images for each scene."""
    print_header()
    job_record = _load_job_record(job_id)

    if not job_record.scene_plan_path:
        console.print("[red]Error: No scene plan found for this job[/red]")
        raise typer.Exit(code=1)

    scene_plan = load_json(Path(job_record.scene_plan_path))
    console.print(f"[bold]Generating {len(scene_plan['scenes'])} images for scenes...[/bold]")

    stage = ImageGenerationStage(job_id=job_id, mock=mock, placeholder_only=placeholder_only)
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
        console.print("[red]Error: No script found for this job[/red]")
        raise typer.Exit(code=1)

    script_data = load_json(Path(job_record.script_path))
    stage = SubtitleStage(job_id=job_id, mock=mock)
    result = asyncio.run(stage.run(script_data, job_record.audio_path))
    stage.save_subtitles(result)

    db.update_job(job_id, status="subtitles_complete", subtitle_path=result.srt_path)

    console.print()
    console.print("[bold green]Subtitles Complete![/bold green]")
    console.print(f"[dim]Segments:[/dim] {len(result.segments)}")
    console.print(f"[dim]Next step:[/dim] python -m src.main render {job_id}")


@app.command()
def render(
    job_id: str = typer.Argument(..., help="Job ID from subtitles stage"),
    mock: bool = typer.Option(False, "--mock", "-m", help="Use mock data"),
    video_mode: VideoMode = typer.Option(VideoMode.LONG, "--video-mode", help="Video mode: short or long"),
) -> None:
    """Render the final video with ffmpeg."""
    print_header()
    job_record = _load_job_record(job_id)

    if not job_record.scene_plan_path:
        console.print("[red]Error: No scene plan found. Run scene stage first.[/red]")
        raise typer.Exit(code=1)
    if not job_record.audio_path:
        console.print("[red]Error: No audio file found. Run TTS stage first.[/red]")
        raise typer.Exit(code=1)
    if not job_record.subtitle_path:
        console.print("[red]Error: No subtitles found. Run subtitles stage first.[/red]")
        raise typer.Exit(code=1)

    scenes_data = load_json(Path(job_record.scene_plan_path)).get("scenes", [])
    scenes = [Scene(**scene) for scene in scenes_data]

    renderer = VideoRenderer(job_id=job_id, mock=mock)
    output_path = renderer.output_dir / "final.mp4"
    width = settings.short_video_width if video_mode == VideoMode.SHORT else settings.video_width
    height = settings.short_video_height if video_mode == VideoMode.SHORT else settings.video_height
    config = VideoRenderConfig(
        scenes=scenes,
        audio_path=job_record.audio_path,
        subtitle_path=job_record.subtitle_path,
        output_path=str(output_path),
        width=width,
        height=height,
    )
    result = asyncio.run(renderer.run(config))

    db.update_job(
        job_id,
        status="render_complete",
        video_path=result.video_path,
        thumbnail_path=result.thumbnail_path,
    )

    console.print()
    console.print("[bold green]Rendering Complete![/bold green]")
    console.print(f"[dim]Video path:[/dim] {result.video_path}")
    console.print(f"[dim]Thumbnail path:[/dim] {result.thumbnail_path}")
    console.print(f"[dim]Next step:[/dim] python -m src.main metadata {job_id}")


@app.command()
def metadata(
    job_id: str = typer.Argument(..., help="Job ID from render stage"),
    mock: bool = typer.Option(False, "--mock", "-m", help="Use mock data"),
) -> None:
    """Generate YouTube metadata (title, description, tags, chapters)."""
    print_header()
    job_record = _load_job_record(job_id)

    if not job_record.script_path:
        console.print("[red]Error: No script found for this job[/red]")
        raise typer.Exit(code=1)

    script_data = load_json(Path(job_record.script_path))
    uploader = YouTubeUploader(mock=mock)
    metadata_payload = uploader.generate_metadata(
        script_title=script_data["title"],
        chapters=script_data.get("chapters", []),
    )
    metadata_path = _save_metadata(job_id, metadata_payload)

    console.print()
    console.print("[bold green]Metadata Complete![/bold green]")
    console.print(f"[dim]Title:[/dim] {metadata_payload['title']}")
    console.print(f"[dim]Tags:[/dim] {len(metadata_payload['tags'])}")
    console.print(f"[dim]Metadata path:[/dim] {metadata_path}")
    console.print(f"[dim]Next step:[/dim] python -m src.main upload {job_id}")


@app.command()
def upload(
    job_id: str = typer.Argument(..., help="Job ID from metadata stage"),
    mock: bool = typer.Option(False, "--mock", "-m", help="Use mock data"),
) -> None:
    """Upload video to YouTube."""
    print_header()
    job_record = _load_job_record(job_id)

    if not job_record.video_path:
        console.print("[red]Error: No video found. Run render stage first.[/red]")
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

    metadata_payload = load_json(Path(job_record.metadata_path))
    uploader = YouTubeUploader(mock=mock)
    result = asyncio.run(
        uploader.upload(
            video_path=job_record.video_path,
            metadata=metadata_payload,
            thumbnail_path=job_record.thumbnail_path,
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


@app.command()
def run(
    topic: str = typer.Argument(..., help="Topic for the video"),
    mock: bool = typer.Option(False, "--mock", "-m", help="Use mock data for all stages"),
    provider: str = typer.Option("edge", "--provider", "-p", help="TTS provider (local, edge, or elevenlabs)"),
    skip_upload: bool = typer.Option(False, "--skip-upload", help="Run the full pipeline but skip the upload stage"),
    video_mode: VideoMode = typer.Option(settings.default_video_mode, "--video-mode", help="Video mode: short or long"),
    placeholder_images: bool = typer.Option(False, "--placeholder-images", help="Skip sd-cli and generate local placeholder scene cards"),
) -> None:
    """Run the complete pipeline for a topic."""
    job_record = db.create_job(topic)
    job_id = job_record.job_id

    with job_output_capture(job_id):
        print_header()
        console.print(f"[bold]Running complete pipeline for:[/bold] {topic}")
        if skip_upload:
            console.print("[yellow]Upload stage will be skipped[/yellow]")
        if placeholder_images:
            console.print("[yellow]Using placeholder scene cards instead of sd-cli[/yellow]")

        research_stage_mock = mock or settings.mock_mode
        script_stage_mock = mock or settings.mock_mode
        scene_stage_mock = mock or settings.mock_mode
        media_stage_mock = mock or settings.mock_mode

        if not mock and not settings.mock_mode:
            console.print(
                f"[yellow]Using hybrid local mode: real research + real script + mock scene planner + real local media generation ({video_mode.value})[/yellow]"
            )
            research_stage_mock = False
            script_stage_mock = False
            scene_stage_mock = True
            media_stage_mock = False
        else:
            console.print("[yellow]Using mock mode for local-friendly generation[/yellow]")

        console.print(f"[bold]Job ID:[/bold] {job_id}")
        console.print()

        research(topic=topic, job_id=job_id, mock=research_stage_mock)
        script(job_id=job_id, mock=script_stage_mock, video_mode=video_mode)
        scene(job_id=job_id, mock=scene_stage_mock)
        tts(job_id=job_id, provider=provider, mock=media_stage_mock)
        images(job_id=job_id, mock=media_stage_mock, placeholder_only=placeholder_images)
        subtitles(job_id=job_id, mock=media_stage_mock)
        render(job_id=job_id, mock=media_stage_mock, video_mode=video_mode)
        metadata(job_id=job_id, mock=script_stage_mock)

        if not skip_upload:
            upload(job_id=job_id, mock=mock)
        else:
            db.update_job(job_id, status="ready_for_upload")

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
            "script": lambda: script(job_id=job_id, mock=mock),
            "scene": lambda: scene(job_id=job_id, mock=mock),
            "tts": lambda: tts(job_id=job_id, provider=settings.tts_provider.value, mock=mock),
            "images": lambda: images(job_id=job_id, mock=mock),
            "subtitles": lambda: subtitles(job_id=job_id, mock=mock),
            "render": lambda: render(job_id=job_id, mock=mock),
            "metadata": lambda: metadata(job_id=job_id, mock=mock),
            "upload": lambda: upload(job_id=job_id, mock=mock),
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
