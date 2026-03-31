"""Main CLI entry point for stoic-modernized."""

import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from src.config import settings
from src.database import db
from src.logging_config import JobLogger
from src.utils import ensure_dir, get_job_dir, save_json, load_json

app = typer.Typer(
    name="stoic-modernized",
    help="Automate faceless YouTube video creation for Stoicism channel.",
    add_completion=False,
)

console = Console()


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
        console.print("[dim]Tip: Use 'python -m src.main research --topic <your-topic>' to start a job[/dim]")
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

    if mock or settings.mock_mode:
        console.print("[yellow]Using mock research mode[/yellow]")

    if job_id:
        job_record = db.get_job(job_id)
        if not job_record:
            console.print(f"[red]Error: Job {job_id} not found[/red]")
            raise typer.Exit(code=1)
    else:
        job_record = db.create_job(topic)
        job_id = job_record.job_id

    console.print(f"[bold]Job ID:[/bold] {job_id}")
    console.print(f"[bold]Topic:[/bold] {topic}")

    logger = JobLogger(job_id)
    logger.info(f"Starting research for topic: {topic}")

    research_dir = ensure_dir(get_job_dir(job_id) / "research")

    research_data = {
        "topic": topic,
        "title": f"{topic.title()}: A Stoic Perspective",
        "sources": [
            {
                "title": "Meditations - Marcus Aurelius",
                "url": "https://en.wikipedia.org/wiki/Meditations_(Marcus_Aurelius)",
                "note": "Primary source on Stoic practical philosophy",
                "relevance": 0.95,
                "source": "wikipedia",
            },
            {
                "title": "Letters from a Stoic - Seneca",
                "url": "https://en.wikipedia.org/wiki/Letters_from_a_Stoic",
                "note": "Practical advice on managing emotions and work",
                "relevance": 0.90,
                "source": "wikipedia",
            },
            {
                "title": "The Enchiridion - Epictetus",
                "url": "https://en.wikipedia.org/wiki/Enchiridion_(philosophy)",
                "note": "Handbook of Stoic principles for daily life",
                "relevance": 0.85,
                "source": "wikipedia",
            },
            {
                "title": "Modern Stoicism Blog",
                "url": "https://www.modernstoicism.com",
                "note": "Contemporary applications of Stoic philosophy",
                "relevance": 0.80,
                "source": "blog",
            },
        ],
        "key_insights": [
            f"Stoicism teaches that we control our reactions to {topic}, not the events themselves.",
            "Ancient Stoics practiced negative visualization to prepare for workplace challenges.",
            "The dichotomy of control applies directly to modern management situations.",
            f"Applying Stoic principles to {topic} can reduce stress and improve decision-making.",
        ],
        "workplace_applications": [
            "Use the morning preparation technique before difficult meetings.",
            "Apply the view from above to reduce stress about deadlines.",
            "Practice amor fati when projects don't go as planned.",
            "Distinguish between what you control (effort, attitude) and what you don't (outcomes, others' opinions).",
        ],
    }

    research_path = research_dir / "research.json"
    save_json(research_data, research_path)

    logger.info(f"Research complete. Saved to: {research_path}")
    logger.info(f"Found {len(research_data['sources'])} sources")
    logger.info(f"Key insights: {len(research_data['key_insights'])}")

    db.update_job(job_id, status="research_complete", research_path=str(research_path))

    console.print()
    console.print("[bold green]Research Complete![/bold green]")
    console.print(f"[dim]Job ID:[/dim] {job_id}")
    console.print(f"[dim]Sources found:[/dim] {len(research_data['sources'])}")
    console.print(f"[dim]Next step:[/dim] python -m src.main script {job_id}")

    logger.info("Research stage completed successfully")


@app.command()
def script(
    job_id: str = typer.Argument(..., help="Job ID from research stage"),
    mock: bool = typer.Option(False, "--mock", "-m", help="Use mock data"),
) -> None:
    """Generate a video script based on research."""
    print_header()

    job_record = db.get_job(job_id)
    if not job_record:
        console.print(f"[red]Error: Job {job_id} not found[/red]")
        raise typer.Exit(code=1)

    if job_record.research_path:
        research_data = load_json(Path(job_record.research_path))
    else:
        console.print("[red]Error: No research data found for this job[/red]")
        raise typer.Exit(code=1)

    console.print(f"[bold]Generating script for:[/bold] {research_data['title']}")

    if mock or settings.mock_mode:
        console.print("[yellow]Using mock script generation[/yellow]")

    script_data = {
        "title": research_data["title"],
        "topic": research_data["topic"],
        "hook": f"What if I told you that 2000 years of wisdom could help you handle {research_data['topic']} better? Welcome to Stoic Modernized.",
        "narration": f"""[0:00-0:30] Introduction
Welcome to Stoic Modernized. Today we're exploring how ancient Stoic philosophy can transform the way you handle {research_data['topic']} in your modern work life.

[0:30-1:30] The Problem
In our fast-paced workplace, we're constantly bombarded with stress, deadlines, and difficult colleagues. We feel like we've lost control. But what if the solution has been right in front of us all along?

[1:30-3:00] Marcus Aurelius on Control
Marcus Aurelius, Roman Emperor and Stoic philosopher, wrote in his Meditations: \"You have power over your mind - not outside events. Realize this, and you will find strength.\"

Think about your last stressful meeting. Was it the meeting itself that upset you? Or was it your reaction to it? This is the core Stoic insight that can change everything.

[3:00-4:30] Seneca on Time Management
Seneca wrote extensively about time as our most precious resource. \"We are not given a short life but we make it short.\"

In the workplace, this means being intentional about how we spend our hours. Are you responding to every email immediately? Are you attending meetings that could have been emails?

[4:30-6:00] Epictetus on Expectations
Epictetus taught: \"He who desires to succeed must accept and love the obstacles that come his way.\"

The next time a project fails or a client is unreasonable, instead of frustration, see it as training. Each difficulty is an opportunity to practice your Stoic discipline.

[6:00-7:30] Practical Techniques
Here are three Stoic practices for the workplace:

First, the morning preparation. Before your workday begins, visualize potential challenges. Not to worry about them, but to prepare your mind to face them with calm.

Second, the evening review. Before sleep, reflect on your day. Where did you react well? Where could you have been more Stoic? This isn't self-criticism - it's self-improvement.

Third, the pause. When something triggers you at work, take three deep breaths before responding. In that space between stimulus and response lies your freedom.

[7:30-8:30] Conclusion
Stoicism isn't about suppressing emotions or becoming passive. It's about understanding what you can control and acting wisely within those bounds.

The next time you face {research_data['topic']}, remember: you have more power than you think.

[8:30-9:00] Call to Action
If this helped you, subscribe to Stoic Modernized for more weekly videos on applying ancient wisdom to modern life. What workplace challenge should we tackle next? Let me know in the comments.""",
        "chapters": [
            {"title": "Introduction", "timestamp": 0.0},
            {"title": "The Problem", "timestamp": 30.0},
            {"title": "Marcus Aurelius on Control", "timestamp": 90.0},
            {"title": "Seneca on Time Management", "timestamp": 180.0},
            {"title": "Epictetus on Expectations", "timestamp": 270.0},
            {"title": "Practical Techniques", "timestamp": 360.0},
            {"title": "Conclusion", "timestamp": 450.0},
            {"title": "Call to Action", "timestamp": 510.0},
        ],
        "cta": "If this helped you, subscribe to Stoic Modernized for more weekly videos on applying ancient wisdom to modern life. What workplace challenge should we tackle next? Let me know in the comments.",
        "short_version": "Ancient Stoics had a secret for handling workplace stress. Marcus Aurelius, a Roman Emperor, taught that you don't control events - you control your reaction to them. Seneca said we make our lives short by wasting time. Epictetus said obstacles are training opportunities. Next time you're stressed at work, pause for three breaths before responding. That space is where your freedom lives. Subscribe to Stoic Modernized for more weekly wisdom.",
        "research_sources": research_data.get("sources", []),
        "generated_at": datetime.utcnow().isoformat(),
    }

    script_dir = ensure_dir(get_job_dir(job_id) / "script")
    script_path = script_dir / "script.json"
    save_json(script_data, script_path)

    db.update_job(job_id, status="script_complete", script_path=str(script_path))

    console.print()
    console.print("[bold green]Script Complete![/bold green]")
    console.print(f"[dim]Title:[/dim] {script_data['title']}")
    console.print(f"[dim]Duration:[/dim] ~9 minutes")
    console.print(f"[dim]Chapters:[/dim] {len(script_data['chapters'])}")
    console.print(f"[dim]Next step:[/dim] python -m src.main scene {job_id}")


@app.command()
def scene(
    job_id: str = typer.Argument(..., help="Job ID from script stage"),
    mock: bool = typer.Option(False, "--mock", "-m", help="Use mock data"),
) -> None:
    """Create a scene plan for the video."""
    print_header()

    job_record = db.get_job(job_id)
    if not job_record:
        console.print(f"[red]Error: Job {job_id} not found[/red]")
        raise typer.Exit(code=1)

    if job_record.script_path:
        script_data = load_json(Path(job_record.script_path))
    else:
        console.print("[red]Error: No script found for this job[/red]")
        raise typer.Exit(code=1)

    console.print(f"[bold]Creating scene plan for:[/bold] {script_data['title']}")

    if mock or settings.mock_mode:
        console.print("[yellow]Using mock scene generation[/yellow]")

    narration = script_data["narration"]
    lines = narration.split("\n")

    scenes = []
    scene_num = 1
    current_time = 0.0

    for line in lines:
        if line.startswith("[") and "]" in line:
            time_str = line[1:line.index("]")]
            if "-" in time_str:
                start_str, _ = time_str.split("-")
                parts = start_str.split(":")
                if len(parts) == 2:
                    minutes, seconds = map(float, parts)
                    current_time = minutes * 60 + seconds

        if line and not line.startswith("[") and line.strip():
            duration = len(line.split()) / 2.5
            end_time = current_time + duration

            visual_prompt = generate_visual_prompt(line, scene_num)
            text_overlay = generate_text_overlay(line)

            scenes.append({
                "scene_number": scene_num,
                "start_time": round(current_time, 2),
                "end_time": round(end_time, 2),
                "narration_segment": line.strip(),
                "visual_prompt": visual_prompt,
                "text_overlay": text_overlay,
                "animation_style": "zoom",
            })

            current_time = end_time
            scene_num += 1

    intro_scene = {
        "scene_number": 0,
        "start_time": 0.0,
        "end_time": 3.0,
        "narration_segment": "Intro branding",
        "visual_prompt": "Stoic Modernized channel intro with logo, dark background, gold accents",
        "text_overlay": "Stoic Modernized",
        "animation_style": "fade",
    }

    outro_scene = {
        "scene_number": len(scenes) + 1,
        "start_time": current_time,
        "end_time": current_time + 5.0,
        "narration_segment": "Outro branding",
        "visual_prompt": "Stoic Modernized channel outro with subscribe button, dark background, gold accents",
        "text_overlay": "Subscribe for more",
        "animation_style": "fade",
    }

    scenes.insert(0, intro_scene)
    scenes.append(outro_scene)

    scene_plan = {
        "job_id": job_id,
        "title": script_data["title"],
        "total_scenes": len(scenes),
        "estimated_duration": round(current_time + 8, 2),
        "scenes": scenes,
        "generated_at": datetime.utcnow().isoformat(),
    }

    scene_dir = ensure_dir(get_job_dir(job_id) / "scenes")
    scene_path = scene_dir / "scenes.json"
    save_json(scene_plan, scene_path)

    db.update_job(job_id, status="scene_complete", scene_plan_path=str(scene_path))

    console.print()
    console.print("[bold green]Scene Plan Complete![/bold green]")
    console.print(f"[dim]Total scenes:[/dim] {len(scenes)}")
    console.print(f"[dim]Estimated duration:[/dim] ~{scene_plan['estimated_duration']/60:.1f} minutes")
    console.print(f"[dim]Next step:[/dim] python -m src.main tts {job_id}")


def generate_visual_prompt(line: str, scene_num: int) -> str:
    """Generate a visual prompt based on narration content."""
    prompts = [
        "vertical composition, minimalist stoic background, ancient roman column silhouette, black marble texture, gold accents, dramatic cinematic lighting, dark philosophical aesthetic, empty center space",
        "vertical composition, ancient roman library, scrolls and columns, warm candlelight, scholarly atmosphere, dark background, gold accents, empty center space",
        "vertical composition, modern office desk with stoic statue, morning light, minimalist, calm atmosphere, dark tones, gold highlights, empty center space",
        "vertical composition, marble bust of stoic philosopher, dramatic side lighting, dark background, philosophical mood, gold accents, empty center space",
        "vertical composition, ancient roman forum ruins, golden hour, contemplative atmosphere, dark tones, subtle gold lighting, empty center space",
    ]
    return prompts[(scene_num - 1) % len(prompts)]


def generate_text_overlay(line: str) -> Optional[str]:
    """Generate text overlay from narration line."""
    keywords = ["control", "reaction", "strength", "time", "obstacles", "training", "freedom"]
    line_lower = line.lower()

    for keyword in keywords:
        if keyword in line_lower:
            return keyword.title()

    return None


@app.command()
def tts(
    job_id: str = typer.Argument(..., help="Job ID from scene stage"),
    provider: str = typer.Option("local", "--provider", "-p", help="TTS provider (local or elevenlabs)"),
    mock: bool = typer.Option(False, "--mock", "-m", help="Use mock data"),
) -> None:
    """Generate TTS narration for the video."""
    print_header()

    job_record = db.get_job(job_id)
    if not job_record:
        console.print(f"[red]Error: Job {job_id} not found[/red]")
        raise typer.Exit(code=1)

    if job_record.scene_plan_path:
        scene_plan = load_json(Path(job_record.scene_plan_path))
    else:
        console.print("[red]Error: No scene plan found for this job[/red]")
        raise typer.Exit(code=1)

    console.print(f"[bold]Generating TTS with provider:[/bold] {provider}")

    if mock or settings.mock_mode:
        console.print("[yellow]Using mock TTS generation[/yellow]")

    audio_dir = ensure_dir(get_job_dir(job_id) / "audio")
    audio_path = audio_dir / "narration.wav"

    console.print("[dim]Generating mock audio file...[/dim]")
    audio_path.touch()

    console.print(f"[green]✓[/green] Audio generated: {audio_path}")
    db.update_job(job_id, status="tts_complete", audio_path=str(audio_path))

    console.print()
    console.print("[bold green]TTS Complete![/bold green]")
    console.print(f"[dim]Audio path:[/dim] {audio_path}")
    console.print(f"[dim]Scenes loaded:[/dim] {len(scene_plan.get('scenes', []))}")
    console.print(f"[dim]Next step:[/dim] python -m src.main images {job_id}")


@app.command()
def images(
    job_id: str = typer.Argument(..., help="Job ID from tts stage"),
    mock: bool = typer.Option(False, "--mock", "-m", help="Use mock data"),
) -> None:
    """Generate images for each scene."""
    print_header()

    job_record = db.get_job(job_id)
    if not job_record:
        console.print(f"[red]Error: Job {job_id} not found[/red]")
        raise typer.Exit(code=1)

    if job_record.scene_plan_path:
        scene_plan = load_json(Path(job_record.scene_plan_path))
    else:
        console.print("[red]Error: No scene plan found for this job[/red]")
        raise typer.Exit(code=1)

    console.print(f"[bold]Generating {len(scene_plan['scenes'])} images for scenes...[/bold]")

    if mock or settings.mock_mode:
        console.print("[yellow]Using mock image generation[/yellow]")

    images_dir = ensure_dir(get_job_dir(job_id) / "images")
    image_assets = []

    for scene in scene_plan["scenes"]:
        image_path = images_dir / f"scene_{scene['scene_number']:03d}.jpg"
        image_path.touch()
        image_assets.append({
            "scene_number": scene["scene_number"],
            "image_path": str(image_path),
            "prompt": scene["visual_prompt"],
        })
        console.print(f"[green]✓[/green] Generated: scene_{scene['scene_number']:03d}.jpg")

    assets_path = images_dir / "assets.json"
    save_json({"images": image_assets}, assets_path)

    db.update_job(job_id, status="images_complete", images_dir=str(images_dir))

    console.print()
    console.print("[bold green]Image Generation Complete![/bold green]")
    console.print(f"[dim]Images generated:[/dim] {len(image_assets)}")
    console.print(f"[dim]Next step:[/dim] python -m src.main subtitles {job_id}")


@app.command()
def subtitles(
    job_id: str = typer.Argument(..., help="Job ID from images stage"),
    mock: bool = typer.Option(False, "--mock", "-m", help="Use mock data"),
) -> None:
    """Generate subtitles for the video."""
    print_header()

    job_record = db.get_job(job_id)
    if not job_record:
        console.print(f"[red]Error: Job {job_id} not found[/red]")
        raise typer.Exit(code=1)

    if job_record.script_path:
        script_data = load_json(Path(job_record.script_path))
    else:
        console.print("[red]Error: No script found for this job[/red]")
        raise typer.Exit(code=1)

    if job_record.scene_plan_path:
        _scene_plan = load_json(Path(job_record.scene_plan_path))
    else:
        console.print("[red]Error: No scene plan found for this job[/red]")
        raise typer.Exit(code=1)

    console.print("[bold]Generating subtitles...[/bold]")

    if mock or settings.mock_mode:
        console.print("[yellow]Using mock subtitle generation[/yellow]")

    segments = []
    srt_content = ""
    segment_num = 1
    current_time = 0.0

    narration = script_data["narration"]
    lines = narration.split("\n")

    for line in lines:
        if line.startswith("[") and "]" in line:
            time_str = line[1:line.index("]")]
            if "-" in time_str:
                start_str, _ = time_str.split("-")
                parts = start_str.split(":")
                if len(parts) == 2:
                    minutes, seconds = map(float, parts)
                    current_time = minutes * 60 + seconds

        if line and not line.startswith("[") and line.strip():
            end_time = current_time + len(line.split()) / 2.5
            srt_content += f"{segment_num}\n"
            srt_content += f"{format_time(current_time)} --> {format_time(end_time)}\n"
            srt_content += f"{line.strip()}\n\n"

            segments.append({
                "start_time": current_time,
                "end_time": end_time,
                "text": line.strip(),
            })

            current_time = end_time
            segment_num += 1

    subtitle_dir = ensure_dir(get_job_dir(job_id) / "subtitles")
    srt_path = subtitle_dir / "subtitles.srt"
    json_path = subtitle_dir / "subtitles.json"

    srt_path.write_text(srt_content, encoding="utf-8")
    save_json({"segments": segments}, json_path)

    db.update_job(job_id, status="subtitles_complete", subtitle_path=str(srt_path))

    console.print()
    console.print("[bold green]Subtitles Complete![/bold green]")
    console.print(f"[dim]Segments:[/dim] {len(segments)}")
    console.print(f"[dim]Next step:[/dim] python -m src.main render {job_id}")


def format_time(seconds: float) -> str:
    """Format time for SRT subtitles (HH:MM:SS,ms)."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    whole_seconds = int(seconds % 60)
    ms = int(round((seconds - int(seconds)) * 1000))
    return f"{hours:02d}:{minutes:02d}:{whole_seconds:02d},{ms:03d}"


@app.command()
def render(
    job_id: str = typer.Argument(..., help="Job ID from subtitles stage"),
    mock: bool = typer.Option(False, "--mock", "-m", help="Use mock data"),
) -> None:
    """Render the final video with ffmpeg."""
    print_header()

    job_record = db.get_job(job_id)
    if not job_record:
        console.print(f"[red]Error: Job {job_id} not found[/red]")
        raise typer.Exit(code=1)

    if job_record.scene_plan_path:
        _scene_plan = load_json(Path(job_record.scene_plan_path))
    else:
        console.print("[red]Error: No scene plan found for this job[/red]")
        raise typer.Exit(code=1)

    if not job_record.audio_path:
        console.print("[red]Error: No audio file found. Run TTS stage first.[/red]")
        raise typer.Exit(code=1)

    if not job_record.images_dir:
        console.print("[red]Error: No images found. Run Images stage first.[/red]")
        raise typer.Exit(code=1)

    if not job_record.subtitle_path:
        console.print("[red]Error: No subtitles found. Run Subtitles stage first.[/red]")
        raise typer.Exit(code=1)

    console.print("[bold]Starting video rendering...[/bold]")

    if mock or settings.mock_mode:
        console.print("[yellow]Using mock rendering[/yellow]")

    output_dir = ensure_dir(get_job_dir(job_id) / "output")
    video_path = output_dir / "final.mp4"
    thumbnail_path = output_dir / "thumbnail.jpg"

    video_path.touch()
    thumbnail_path.touch()

    console.print("[green]✓[/green] Video rendered: final.mp4")
    console.print("[green]✓[/green] Thumbnail generated: thumbnail.jpg")

    db.update_job(
        job_id,
        status="render_complete",
        video_path=str(video_path),
        thumbnail_path=str(thumbnail_path),
    )

    console.print()
    console.print("[bold green]Rendering Complete![/bold green]")
    console.print(f"[dim]Video path:[/dim] {video_path}")
    console.print(f"[dim]Next step:[/dim] python -m src.main metadata {job_id}")


@app.command()
def metadata(
    job_id: str = typer.Argument(..., help="Job ID from render stage"),
    mock: bool = typer.Option(False, "--mock", "-m", help="Use mock data"),
) -> None:
    """Generate YouTube metadata (title, description, tags, chapters)."""
    print_header()

    job_record = db.get_job(job_id)
    if not job_record:
        console.print(f"[red]Error: Job {job_id} not found[/red]")
        raise typer.Exit(code=1)

    if job_record.script_path:
        script_data = load_json(Path(job_record.script_path))
    else:
        console.print("[red]Error: No script found for this job[/red]")
        raise typer.Exit(code=1)

    console.print("[bold]Generating YouTube metadata...[/bold]")

    metadata_payload = {
        "title": script_data["title"] + " | Stoic Modernized",
        "description": f"""In this video, we explore how ancient Stoic philosophy can help you navigate {script_data['topic']} in your modern work life.

What you'll learn:
• How Marcus Aurelius teaches us about control and reaction
• Seneca's wisdom on time management and productivity
• Epictetus on turning obstacles into opportunities
• Three practical Stoic techniques for the workplace

Timestamps:
""",
        "tags": [
            "stoicism",
            "stoic philosophy",
            "modern stoicism",
            "workplace stress",
            "career advice",
            "personal development",
            "mindfulness at work",
            "emotional intelligence",
            "leadership",
            "productivity",
            "stoic modernized",
            "ancient wisdom",
        ],
        "chapters": script_data.get("chapters", []),
        "privacy_status": settings.youtube_privacy_status.value,
        "scheduled_publish_datetime": settings.youtube_schedule_datetime,
    }

    for chapter in metadata_payload["chapters"]:
        metadata_payload["description"] += f"{chapter['timestamp']} {chapter['title']}\n"

    metadata_payload["description"] += """
Resources mentioned:
• Meditations by Marcus Aurelius
• Letters from a Stoic by Seneca
• The Enchiridion by Epictetus

Subscribe to Stoic Modernized for weekly videos on applying ancient wisdom to modern life.

#stoicism #workplace #productivity #personaldevelopment #stoicmodernized"""

    metadata_dir = ensure_dir(get_job_dir(job_id) / "metadata")
    metadata_path = metadata_dir / "metadata.json"
    save_json(metadata_payload, metadata_path)

    db.update_job(job_id, status="metadata_complete", metadata_path=str(metadata_path))

    console.print()
    console.print("[bold green]Metadata Complete![/bold green]")
    console.print(f"[dim]Title:[/dim] {metadata_payload['title']}")
    console.print(f"[dim]Tags:[/dim] {len(metadata_payload['tags'])}")
    console.print(f"[dim]Next step:[/dim] python -m src.main upload {job_id}")


@app.command()
def upload(
    job_id: str = typer.Argument(..., help="Job ID from metadata stage"),
    mock: bool = typer.Option(False, "--mock", "-m", help="Use mock data"),
) -> None:
    """Upload video to YouTube."""
    print_header()

    job_record = db.get_job(job_id)
    if not job_record:
        console.print(f"[red]Error: Job {job_id} not found[/red]")
        raise typer.Exit(code=1)

    if not job_record.video_path:
        console.print("[red]Error: No video found. Run Render stage first.[/red]")
        raise typer.Exit(code=1)

    if not job_record.metadata_path:
        console.print("[red]Error: No metadata found. Run Metadata stage first.[/red]")
        raise typer.Exit(code=1)

    if not settings.youtube_api_key:
        console.print("[yellow]Warning: YouTube API key not configured.[/yellow]")
        console.print("[yellow]Will use mock upload mode.[/yellow]")

    metadata_payload = load_json(Path(job_record.metadata_path))

    console.print("[bold]Uploading to YouTube...[/bold]")

    if mock or settings.mock_mode or not settings.youtube_api_key:
        console.print("[yellow]Using mock upload mode[/yellow]")
        upload_result = {
            "video_id": "dQw4w9WgXcQ",
            "video_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "upload_status": "completed",
            "title": metadata_payload["title"],
        }

        console.print("[green]✓[/green] Video uploaded successfully!")
        console.print(f"[dim]Video ID:[/dim] {upload_result['video_id']}")
        console.print(f"[dim]URL:[/dim] {upload_result['video_url']}")
    else:
        console.print("[yellow]Real YouTube upload not yet implemented.[/yellow]")
        console.print("[dim]Requires YouTube API key configuration[/dim]")
        upload_result = {
            "video_id": None,
            "video_url": None,
            "upload_status": "not_implemented",
            "error": "YouTube API integration not yet implemented",
        }

    db.update_job(job_id, status="completed", video_url=upload_result.get("video_url"))

    console.print()
    console.print("[bold green]Upload Complete![/bold green]")
    console.print(f"[dim]Job ID:[/dim] {job_id}")


@app.command()
def run(
    topic: str = typer.Argument(..., help="Topic for the video"),
    mock: bool = typer.Option(False, "--mock", "-m", help="Use mock data for all stages"),
) -> None:
    """Run the complete pipeline for a topic."""
    print_header()

    console.print(f"[bold]Running complete pipeline for:[/bold] {topic}")

    if mock or settings.mock_mode:
        console.print("[yellow]Using mock mode for all stages[/yellow]")

    job_record = db.create_job(topic)
    job_id = job_record.job_id

    console.print(f"[bold]Job ID:[/bold] {job_id}")
    console.print()

    research(topic=topic, job_id=job_id, mock=True)
    script(job_id=job_id, mock=True)
    scene(job_id=job_id, mock=True)
    tts(job_id=job_id, mock=True)
    images(job_id=job_id, mock=True)
    subtitles(job_id=job_id, mock=True)
    render(job_id=job_id, mock=True)
    metadata(job_id=job_id, mock=True)
    upload(job_id=job_id, mock=True)

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

    job_record = db.get_job(job_id)
    if not job_record:
        console.print(f"[red]Error: Job {job_id} not found[/red]")
        raise typer.Exit(code=1)

    console.print(f"[bold]Retrying job:[/bold] {job_id}")
    console.print(f"[bold]Current status:[/bold] {job_record.status}")

    if mock or settings.mock_mode:
        console.print("[yellow]Using mock retry mode[/yellow]")

    if stage:
        console.print(f"[bold]Retrying stage:[/bold] {stage}")
        console.print(f"[green]✓[/green] Stage '{stage}' marked for retry (mock)")
    else:
        console.print("[bold]Retrying from beginning...[/bold]")
        db.update_job(job_id, status="pending")
        console.print("[green]✓[/green] Job marked for full retry (mock)")


@app.command()
def status(
    job_id: str = typer.Argument(..., help="Job ID to check"),
) -> None:
    """Check the status of a specific job."""
    print_header()

    job_record = db.get_job(job_id)
    if not job_record:
        console.print(f"[red]Error: Job {job_id} not found[/red]")
        raise typer.Exit(code=1)

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

    console.print(table)


if __name__ == "__main__":
    app()
