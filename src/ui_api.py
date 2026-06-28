from __future__ import annotations

import logging
import mimetypes
import re
import shutil
import subprocess
import sys
import threading
import uuid

import httpx
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from src.config import Channel, settings
from src.database import db
from src.stages.news_fetcher import NewsFetcher, StorySummary
from src.stages.social_distribution import channel_job_roots, media_explorer_public_root
from scripts.generate_social_public_explorer import generate_explorer

BASE_DIR = Path(__file__).parent.parent
FRONTEND_DIST = BASE_DIR / "frontend" / "dist"

app = FastAPI(title="Stoic Modernized API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

RUNS: dict[str, dict[str, Any]] = {}
logger = logging.getLogger(__name__)
PYTHON_BIN = sys.executable or "python3"


def refresh_media_explorer() -> str | None:
    """Regenerate the public media explorer after job tree mutations."""
    try:
        return str(generate_explorer(public_root=media_explorer_public_root(), channel_job_roots=channel_job_roots()))
    except Exception as exc:
        logger.warning("Could not refresh media explorer: %s", exc)
        return None


class RunRequest(BaseModel):
    topic: str
    video_mode: str = "short"
    provider: str = "edge"
    channel: str = Channel.STOIC_MODERNIZED.value
    platform: str | None = None
    skip_upload: bool = True
    renderer: str = "remotion"


class StepsRequest(BaseModel):
    topic: str = "workplace stress"
    job_id: str | None = None
    video_mode: str = "short"
    provider: str = "edge"
    channel: str = Channel.STOIC_MODERNIZED.value
    platform: str | None = None
    steps: list[str]
    renderer: str = "remotion"


class FileUpdateRequest(BaseModel):
    content: str


class TopicSuggestionRequest(BaseModel):
    current_topic: str | None = None
    channel: str = Channel.STOIC_MODERNIZED.value


class UploadAssetRequest(BaseModel):
    asset_path: str
    mock: bool = False


class NewsSelectionRequest(BaseModel):
    indices: list[int]


class NewsGenerateRequest(BaseModel):
    channel: str = Channel.STOIC_MODERNIZED.value
    topic: str = "managing work stress"
    video_mode: str = "short"
    provider: str = "edge"
    renderer: str = "remotion"
    skip_upload: bool = False
    platform: str | None = None


def _normalize_topic_line(value: str) -> str:
    cleaned = value.strip().strip(' -\"')
    cleaned = re.sub(r'^[0-9]+[.)]\s*', '', cleaned)
    return cleaned[:160].strip()


def _extract_topic_from_reasoning(reasoning: str) -> str | None:
    lines = [line.strip() for line in reasoning.splitlines() if line.strip()]

    preferred_patterns = (
        re.compile(r'^(?:idea|topic)\s*:\s*(.+)$', re.IGNORECASE),
        re.compile(r'^\*\s*(How to|The Stoic|Stoic|Why |Managing |Setting |Emotional ).+$', re.IGNORECASE),
    )

    candidates: list[str] = []
    for line in lines:
        for pattern in preferred_patterns:
            match = pattern.match(line)
            if match:
                candidate = _normalize_topic_line(match.group(1) if match.lastindex else line.lstrip('* ').strip())
                if candidate and len(candidate.split()) >= 3:
                    candidates.append(candidate)
                    break

    if candidates:
        return candidates[-1]

    for line in reversed(lines):
        candidate = _normalize_topic_line(line)
        if candidate and len(candidate.split()) >= 3 and 'thinking process' not in candidate.lower():
            return candidate

    return None


def _spawn_command(cmd: list[str]) -> str:
    run_id = str(uuid.uuid4())
    process = subprocess.Popen(
        cmd,
        cwd=str(BASE_DIR),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    RUNS[run_id] = {"process": process, "cmd": cmd, "lines": []}

    def pump() -> None:
        assert process.stdout is not None
        for line in process.stdout:
            RUNS[run_id]["lines"].append(line.rstrip("\n"))
        process.wait()
        RUNS[run_id]["returncode"] = process.returncode

    threading.Thread(target=pump, daemon=True).start()
    return run_id


def _read_job_context(job_id: str) -> dict[str, Any]:
    job_context_path = settings.jobs_dir / job_id / "job.json"
    if not job_context_path.exists():
        return {}
    try:
        import json

        data = json.loads(job_context_path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/jobs")
def list_jobs() -> list[dict[str, Any]]:
    jobs = db.get_all_jobs()
    items: list[dict[str, Any]] = []
    for job in jobs:
        context = _read_job_context(job.job_id)
        items.append(
            {
                "job_id": job.job_id,
                "topic": job.topic,
                "status": job.status,
                "created_at": str(job.created_at),
                "channel": context.get("channel", settings.default_channel.value),
                "channel_name": context.get("channel_name", settings.get_channel_name(settings.default_channel)),
                "video_path": job.video_path,
                "thumbnail_path": job.thumbnail_path,
                "subtitle_path": job.subtitle_path,
            }
        )
    return items


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str) -> dict[str, Any]:
    job = db.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    job_dir = settings.jobs_dir / job_id
    assets = []
    if job_dir.exists():
        for path in sorted(job_dir.rglob("*")):
            if path.is_file():
                mime, _ = mimetypes.guess_type(path.name)
                assets.append(
                    {
                        "path": str(path),
                        "relative": str(path.relative_to(job_dir)),
                        "size": path.stat().st_size,
                        "mime": mime or "application/octet-stream",
                        "url": f"/api/jobs/{job_id}/assets/{path.relative_to(job_dir).as_posix()}",
                    }
                )
    context = _read_job_context(job_id)
    return {
        "job_id": job.job_id,
        "topic": job.topic,
        "status": job.status,
        "created_at": str(job.created_at),
        "channel": context.get("channel", settings.default_channel.value),
        "channel_name": context.get("channel_name", settings.get_channel_name(settings.default_channel)),
        "channel_handle": context.get("channel_handle", settings.get_channel_handle(settings.default_channel)),
        "channel_description": context.get("channel_description", settings.get_channel_description(settings.default_channel)),
        "video_path": job.video_path,
        "thumbnail_path": job.thumbnail_path,
        "subtitle_path": job.subtitle_path,
        "research_path": job.research_path,
        "script_path": job.script_path,
        "scene_plan_path": job.scene_plan_path,
        "audio_path": job.audio_path,
        "images_dir": job.images_dir,
        "metadata_path": job.metadata_path,
        "assets": assets,
    }


@app.delete("/api/jobs/{job_id}")
def delete_job(job_id: str) -> dict[str, Any]:
    job = db.get_job(job_id)
    job_dir = settings.jobs_dir / job_id

    removed_dir = False
    if job_dir.exists():
        shutil.rmtree(job_dir)
        removed_dir = True

    removed_db = db.delete_job(job_id)
    explorer_path = refresh_media_explorer()

    if not removed_dir and not removed_db and not job:
        raise HTTPException(status_code=404, detail="Job not found")

    return {
        "deleted": True,
        "job_id": job_id,
        "removed_dir": removed_dir,
        "removed_db": removed_db,
        "media_explorer_path": explorer_path,
    }


def _resolve_job_asset(job_id: str, asset_path: str) -> Path:
    job_dir = settings.jobs_dir / job_id
    path = (job_dir / asset_path).resolve()
    if not path.exists() or (job_dir.resolve() not in path.parents and path != job_dir.resolve()):
        raise HTTPException(status_code=404, detail="Asset not found")
    return path


@app.get("/api/jobs/{job_id}/assets/{asset_path:path}")
def get_job_asset(job_id: str, asset_path: str):
    path = _resolve_job_asset(job_id, asset_path)
    return FileResponse(path)


@app.post("/api/jobs/{job_id}/upload")
def upload_job_asset(job_id: str, request: UploadAssetRequest) -> dict[str, str]:
    job = db.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    asset_path = _resolve_job_asset(job_id, request.asset_path)
    mime, _ = mimetypes.guess_type(asset_path.name)
    if not ((mime or "").startswith("video/") or asset_path.suffix.lower() in {".mp4", ".mov", ".mkv", ".webm"}):
        raise HTTPException(status_code=400, detail="Selected asset is not a video file")
    if not job.metadata_path:
        raise HTTPException(status_code=400, detail="No metadata found. Run metadata first.")

    cmd = [PYTHON_BIN, "-m", "src.main", "upload", job_id, "--video-path", str(asset_path)]
    if request.mock:
        cmd.append("--mock")
    return {"run_id": _spawn_command(cmd)}


@app.post("/api/runs")
def start_run(request: RunRequest) -> dict[str, str]:
    cmd = [
        PYTHON_BIN,
        "-m",
        "src.main",
        "run",
        request.topic,
        "--video-mode",
        request.video_mode,
        "--provider",
        request.provider,
        "--channel",
        request.channel,
    ]
    if request.renderer == "both":
        # Spawn a single process with --renderer both; CLI handles
        # sequential remotion→ffmpeg render pass in one pipeline
        run_cmd = cmd + ["--renderer", "both"]
        if request.platform:
            run_cmd += ["--platform", request.platform]
        if request.skip_upload:
            run_cmd.append("--skip-upload")
        return {"run_id": _spawn_command(run_cmd)}
    else:
        if request.renderer:
            cmd += ["--renderer", request.renderer]
        if request.platform:
            cmd += ["--platform", request.platform]
        if request.skip_upload:
            cmd.append("--skip-upload")
        return {"run_id": _spawn_command(cmd)}


@app.post("/api/runs/steps")
def start_steps(request: StepsRequest) -> dict[str, str | None]:
    commands: list[list[str]] = []
    current_job_id = request.job_id

    for step in request.steps:
        if step == "research":
            cmd = [PYTHON_BIN, "-m", "src.main", "research", request.topic, "--channel", request.channel]
            if current_job_id:
                cmd += ["--job-id", current_job_id]
            commands.append(cmd)
        elif step == "script":
            commands.append([PYTHON_BIN, "-m", "src.main", "script", current_job_id or "", "--video-mode", request.video_mode, "--channel", request.channel])
        elif step == "scene":
            commands.append([PYTHON_BIN, "-m", "src.main", "scene", current_job_id or "", "--channel", request.channel])
        elif step == "tts":
            commands.append([PYTHON_BIN, "-m", "src.main", "tts", current_job_id or "", "--provider", request.provider, "--channel", request.channel])
        elif step == "music":
            commands.append([PYTHON_BIN, "-m", "src.main", "music", current_job_id or ""])
        elif step == "images":
            commands.append([PYTHON_BIN, "-m", "src.main", "images", current_job_id or "", "--channel", request.channel])
        elif step == "subtitles":
            commands.append([PYTHON_BIN, "-m", "src.main", "subtitles", current_job_id or ""])
        elif step == "render":
            renderers = ("remotion", "ffmpeg") if request.renderer == "both" else (request.renderer or "remotion",)
            for r in renderers:
                cmd = [PYTHON_BIN, "-m", "src.main", "render", current_job_id or "", "--video-mode", request.video_mode, "--renderer", r, "--channel", request.channel]
                if request.platform:
                    cmd += ["--platform", request.platform]
                commands.append(cmd)
        elif step == "metadata":
            commands.append([PYTHON_BIN, "-m", "src.main", "metadata", current_job_id or "", "--channel", request.channel])
        elif step == "upload":
            commands.append([PYTHON_BIN, "-m", "src.main", "upload", current_job_id or "", "--channel", request.channel])

    shell_cmd = " && ".join(" ".join(part for part in cmd if part) for cmd in commands)
    return {"run_id": _spawn_command(["bash", "-lc", shell_cmd]), "job_id": current_job_id}


@app.get("/api/runs/{run_id}")
def get_run(run_id: str) -> dict[str, Any]:
    run = RUNS.get(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    process: subprocess.Popen[str] = run["process"]
    return {
        "run_id": run_id,
        "cmd": run["cmd"],
        "running": process.poll() is None,
        "returncode": process.poll(),
        "lines": run["lines"][-500:],
    }


@app.post("/api/runs/{run_id}/stop")
def stop_run(run_id: str) -> dict[str, bool]:
    run = RUNS.get(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    process: subprocess.Popen[str] = run["process"]
    if process.poll() is None:
        process.terminate()
    return {"stopped": True}




@app.post("/api/topics/suggest")
async def suggest_topic(request: TopicSuggestionRequest) -> dict[str, Any]:
    current_topic = (request.current_topic or '').strip()
    # Stoic Modernized topic suggestion prompt
    prompt = f"""
You suggest one topic for a faceless YouTube channel called Stoic Modernized.
The audience is modern workers dealing with stress, work pressure, boundaries, focus, ambition, burnout, and emotional resilience.
Return exactly one concise topic title, no numbering, no quotes, no markdown.
Keep it practical, modern, and specific.

Current topic hint: {current_topic or 'none'}
""".strip()

    try:
        async with httpx.AsyncClient(timeout=settings.local_llm_timeout_seconds) as client:
            response = await client.post(
                settings.local_llm_base_url,
                json={
                    'model': settings.local_llm_model,
                    'messages': [{'role': 'user', 'content': prompt}],
                    'temperature': 0.4,
                    'max_tokens': settings.local_llm_max_tokens,
                    'chat_template_kwargs': {'enable_thinking': False},
                },
            )
            response.raise_for_status()
            data = response.json()
            choices = data.get('choices') or []
            first_choice = choices[0] if choices else {}
            message = first_choice.get('message') or {}
            reasoning_content = message.get('reasoning_content') if isinstance(message.get('reasoning_content'), str) else ''

            raw_content = None
            for candidate in (
                message.get('content'),
                first_choice.get('text'),
                data.get('content'),
            ):
                if isinstance(candidate, str) and candidate.strip():
                    raw_content = candidate.strip()
                    break

            suggestion = None
            extraction_source = 'content'
            if raw_content:
                lines = [line.strip() for line in raw_content.splitlines() if line.strip()]
                suggestion = _normalize_topic_line(lines[0] if lines else raw_content)
            elif reasoning_content:
                suggestion = _extract_topic_from_reasoning(reasoning_content)
                extraction_source = 'reasoning'

            if not suggestion:
                logger.error('Local topic suggestion returned an unexpected payload: %s', data)
                print(f'[topic-suggest] Unexpected payload: {data!r}', file=sys.stderr, flush=True)
                raise ValueError('Local AI returned an empty or unsupported response payload')

            return {
                'topic': suggestion,
                'source': 'local-ai',
                'thinking': reasoning_content,
                'used_reasoning_fallback': extraction_source == 'reasoning',
                'finish_reason': first_choice.get('finish_reason'),
                'raw_content': raw_content or '',
            }
    except Exception as exc:
        logger.exception('Local topic suggestion failed: %s', exc)
        print(f'[topic-suggest] Local topic suggestion failed: {exc!r}', file=sys.stderr, flush=True)
        return {'topic': '', 'source': 'error', 'error': repr(exc), 'thinking': '', 'used_reasoning_fallback': False, 'finish_reason': None, 'raw_content': ''}


# ── News dashboard state (in-memory, keyed by channel) ──────────────────
_NEWS_STATE: dict[str, dict[str, Any]] = {}


def _news_session_key(channel: str) -> str:
    return f"news:{channel}"


@app.post("/api/news/fetch")
async def fetch_news(
    channel: str = Query(Channel.STOIC_MODERNIZED.value),
    append: bool = Query(False),
) -> dict[str, Any]:
    """Fetch Stoic Modernized research topics."""
    try:
        ch = Channel(channel)
    except Exception:
        ch = Channel.STOIC_MODERNIZED

    session_key = _news_session_key(channel)
    existing_state = _NEWS_STATE.get(session_key) if append else None
    existing_stories = list((existing_state or {}).get("stories", []))
    skip_urls = {
        str(story.get("url") or "").strip().lower().split("#", 1)[0].split("?", 1)[0].rstrip("/")
        for story in existing_stories
        if story.get("url")
    }

    fetcher = NewsFetcher(channel=ch)
    stories = await fetcher.fetch_stories("AI news", summarize=False, skip_urls=skip_urls)
    new_stories = [s.to_dict() for s in stories]
    combined_stories = [*existing_stories, *new_stories] if append else new_stories

    existing_selected = list((existing_state or {}).get("selected_indices", [])) if append else []
    _NEWS_STATE[session_key] = {
        "stories": combined_stories,
        "selected_indices": existing_selected,
        "article_reads": [*((existing_state or {}).get("article_reads", [])), *fetcher.article_reads] if append else fetcher.article_reads,
    }

    return {
        "stories": combined_stories,
        "count": len(combined_stories),
        "added_count": len(new_stories),
    }


@app.post("/api/news/selected")
def save_selected_news(
    request: NewsSelectionRequest,
    channel: str = Query(Channel.AI_SIGNAL.value),
) -> dict[str, Any]:
    """Save the user's selected story indices."""
    session_key = _news_session_key(channel)
    if session_key not in _NEWS_STATE:
        raise HTTPException(status_code=404, detail="No news session. Fetch first.")

    _NEWS_STATE[session_key]["selected_indices"] = request.indices
    return {"selected_count": len(_NEWS_STATE[session_key]["selected_indices"])}


@app.get("/api/news/selected")
def get_selected_news(channel: str = Query(Channel.AI_SIGNAL.value)) -> dict[str, Any]:
    """Return currently selected stories."""
    session_key = _news_session_key(channel)
    if session_key not in _NEWS_STATE:
        raise HTTPException(status_code=404, detail="No news session. Fetch first.")

    state = _NEWS_STATE[session_key]
    selected = [state["stories"][i] for i in state["selected_indices"] if 0 <= i < len(state["stories"])]
    return {"stories": selected, "selected_count": len(selected)}


@app.delete("/api/news/selected")
def clear_selected_news(channel: str = Query(Channel.AI_SIGNAL.value)) -> dict[str, str]:
    """Clear the current news session."""
    session_key = _news_session_key(channel)
    _NEWS_STATE.pop(session_key, None)
    return {"cleared": "true"}


@app.post("/api/news/generate")
def generate_from_selected_news(request: NewsGenerateRequest) -> dict[str, str]:
    """Create research from selected stories, then run remaining pipeline stages in the background."""
    import asyncio
    import json
    import shlex

    from src.models import ResearchSource
    from src.stages.research import ResearchStage

    channel = request.channel
    topic = request.topic
    video_mode = request.video_mode
    provider = request.provider
    renderer = request.renderer
    platform = request.platform

    try:
        ch = Channel(channel)
    except Exception:
        ch = Channel.AI_SIGNAL
        channel = ch.value

    session_key = _news_session_key(channel)
    if session_key not in _NEWS_STATE:
        raise HTTPException(status_code=404, detail="No news session. Fetch first.")

    state = _NEWS_STATE[session_key]
    selected = [state["stories"][i] for i in state["selected_indices"] if 0 <= i < len(state["stories"])]
    if not selected:
        raise HTTPException(status_code=400, detail="No stories selected.")

    job_record = db.create_job(topic)
    job_id = job_record.job_id

    job_dir = settings.jobs_dir / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    context = {
        "job_id": job_id,
        "topic": topic,
        "channel": ch.value,
        "channel_name": settings.get_channel_name(ch),
        "channel_handle": settings.get_channel_handle(ch),
        "channel_description": settings.get_channel_description(ch),
        "channel_voice": settings.get_channel_voice(ch),
    }
    (job_dir / "job.json").write_text(json.dumps(context, indent=2), encoding="utf-8")

    research_sources = [
        ResearchSource(
            title=st["title"],
            url=st["url"],
            note=st.get("summary") or st.get("content") or st.get("snippet") or "",
            relevance=st.get("relevance", 0.9),
            source=st.get("source", "web"),
        )
        for st in selected
    ]

    research_stage = ResearchStage(job_id=job_id, channel=ch, selected_sources=research_sources)
    results = asyncio.run(research_stage.run(topic))
    research_path = research_stage.save_results(results)
    db.update_job(job_id, status="research_complete", research_path=str(research_path))

    q_job = shlex.quote(job_id)
    q_channel = shlex.quote(ch.value)
    q_provider = shlex.quote(provider)
    q_video_mode = shlex.quote(video_mode)
    q_renderer = shlex.quote(renderer)
    platform_arg = f" --platform {shlex.quote(platform)}" if platform else ""
    upload_cmd = "" if request.skip_upload else f" && {shlex.quote(PYTHON_BIN)} -m src.main upload {q_job} --channel {q_channel}"
    cmd = " && ".join([
        f"{shlex.quote(PYTHON_BIN)} -m src.main script {q_job} --video-mode {q_video_mode} --channel {q_channel}",
        f"{shlex.quote(PYTHON_BIN)} -m src.main scene {q_job} --channel {q_channel}",
        f"{shlex.quote(PYTHON_BIN)} -m src.main tts {q_job} --provider {q_provider} --channel {q_channel}",
        f"({shlex.quote(PYTHON_BIN)} -m src.main music {q_job} || true)",
        f"{shlex.quote(PYTHON_BIN)} -m src.main images {q_job} --channel {q_channel}",
        f"{shlex.quote(PYTHON_BIN)} -m src.main subtitles {q_job}",
        f"{shlex.quote(PYTHON_BIN)} -m src.main render {q_job} --video-mode {q_video_mode} --renderer {q_renderer} --channel {q_channel}{platform_arg}",
        f"{shlex.quote(PYTHON_BIN)} -m src.main metadata {q_job} --channel {q_channel}",
    ]) + upload_cmd
    if request.skip_upload:
        cmd += f" && {shlex.quote(PYTHON_BIN)} - <<'PY'\nfrom src.database import db\ndb.update_job('{job_id}', status='ready_for_upload')\nPY"

    run_id = _spawn_command(["bash", "-lc", cmd])
    return {"run_id": run_id, "job_id": job_id}


@app.get("/api/config/env")
def read_env() -> dict[str, str]:
    path = BASE_DIR / ".env"
    return {"content": path.read_text(encoding="utf-8") if path.exists() else ""}


@app.post("/api/config/env")
def save_env(request: FileUpdateRequest) -> dict[str, bool]:
    path = BASE_DIR / ".env"
    path.write_text(request.content, encoding="utf-8")
    return {"saved": True}


@app.get("/api/config/file")
def read_config_file() -> dict[str, str]:
    path = Path(__file__).parent / "config.py"
    return {"content": path.read_text(encoding="utf-8")}


@app.post("/api/config/file")
def save_config_file(request: FileUpdateRequest) -> dict[str, bool]:
    path = Path(__file__).parent / "config.py"
    path.write_text(request.content, encoding="utf-8")
    return {"saved": True}


if FRONTEND_DIST.exists():
    assets_dir = FRONTEND_DIST / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="frontend-assets")

    @app.get("/", include_in_schema=False)
    def frontend_index():
        return FileResponse(FRONTEND_DIST / "index.html")
