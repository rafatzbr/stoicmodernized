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

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from src.config import settings
from src.database import db

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


class RunRequest(BaseModel):
    topic: str
    video_mode: str = "short"
    provider: str = "edge"
    platform: str | None = None
    skip_upload: bool = True
    renderer: str = "ffmpeg"


class StepsRequest(BaseModel):
    topic: str = "workplace stress"
    job_id: str | None = None
    video_mode: str = "short"
    provider: str = "edge"
    platform: str | None = None
    steps: list[str]
    renderer: str = "ffmpeg"


class FileUpdateRequest(BaseModel):
    content: str


class TopicSuggestionRequest(BaseModel):
    current_topic: str | None = None


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


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/jobs")
def list_jobs() -> list[dict[str, Any]]:
    jobs = db.get_all_jobs()
    return [
        {
            "job_id": job.job_id,
            "topic": job.topic,
            "status": job.status,
            "created_at": str(job.created_at),
            "video_path": job.video_path,
            "thumbnail_path": job.thumbnail_path,
            "subtitle_path": job.subtitle_path,
        }
        for job in jobs
    ]


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
    return {
        "job_id": job.job_id,
        "topic": job.topic,
        "status": job.status,
        "created_at": str(job.created_at),
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

    if not removed_dir and not removed_db and not job:
        raise HTTPException(status_code=404, detail="Job not found")

    return {"deleted": True, "job_id": job_id, "removed_dir": removed_dir, "removed_db": removed_db}


@app.get("/api/jobs/{job_id}/assets/{asset_path:path}")
def get_job_asset(job_id: str, asset_path: str):
    job_dir = settings.jobs_dir / job_id
    path = (job_dir / asset_path).resolve()
    if not path.exists() or job_dir.resolve() not in path.parents and path != job_dir.resolve():
        raise HTTPException(status_code=404, detail="Asset not found")
    return FileResponse(path)


@app.post("/api/runs")
def start_run(request: RunRequest) -> dict[str, str]:
    cmd = [
        "python3",
        "-m",
        "src.main",
        "run",
        request.topic,
        "--video-mode",
        request.video_mode,
        "--provider",
        request.provider,
    ]
    if request.renderer == "both":
        # Spawn a single process with --renderer both; CLI handles
        # sequential ffmpeg→remotion render pass in one pipeline
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
            cmd = ["python3", "-m", "src.main", "research", request.topic]
            if current_job_id:
                cmd += ["--job-id", current_job_id]
            commands.append(cmd)
        elif step == "script":
            commands.append(["python3", "-m", "src.main", "script", current_job_id or "", "--video-mode", request.video_mode])
        elif step == "scene":
            commands.append(["python3", "-m", "src.main", "scene", current_job_id or ""])
        elif step == "tts":
            commands.append(["python3", "-m", "src.main", "tts", current_job_id or "", "--provider", request.provider])
        elif step == "music":
            commands.append(["python3", "-m", "src.main", "music", current_job_id or ""])
        elif step == "images":
            commands.append(["python3", "-m", "src.main", "images", current_job_id or ""])
        elif step == "subtitles":
            commands.append(["python3", "-m", "src.main", "subtitles", current_job_id or ""])
        elif step == "render":
            renderers = ("ffmpeg", "remotion") if request.renderer == "both" else (request.renderer or "ffmpeg",)
            for r in renderers:
                cmd = ["python3", "-m", "src.main", "render", current_job_id or "", "--video-mode", request.video_mode, "--renderer", r]
                if request.platform:
                    cmd += ["--platform", request.platform]
                commands.append(cmd)
        elif step == "metadata":
            commands.append(["python3", "-m", "src.main", "metadata", current_job_id or ""])
        elif step == "upload":
            commands.append(["python3", "-m", "src.main", "upload", current_job_id or ""])

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
        fallback = current_topic if current_topic else 'How to Stay Calm When Everything at Work Feels Urgent'
        if fallback == current_topic and current_topic:
            fallback = f'Stoic Strategies for {current_topic.title()}'
        return {'topic': fallback, 'source': 'fallback', 'error': repr(exc), 'thinking': '', 'used_reasoning_fallback': False, 'finish_reason': None, 'raw_content': ''}


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
