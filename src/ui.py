from __future__ import annotations

import html
import os
import subprocess
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from src.config import VideoMode, settings
from src.database import db
from src.utils import load_json

app = FastAPI(title="Stoic Modernized UI")

BASE_DIR = Path(__file__).parent.parent
TEMPLATES_DIR = BASE_DIR / "web"
STATIC_DIR = TEMPLATES_DIR / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


def html_page(title: str, body: str) -> HTMLResponse:
    return HTMLResponse(
        f"""
        <!doctype html>
        <html>
        <head>
          <meta charset='utf-8'>
          <meta name='viewport' content='width=device-width, initial-scale=1'>
          <title>{title}</title>
          <style>
            body {{ font-family: Inter, system-ui, sans-serif; background:#111; color:#eee; margin:0; padding:24px; }}
            h1,h2,h3 {{ margin-top:0; }}
            .grid {{ display:grid; grid-template-columns: 1fr 1fr; gap:20px; }}
            .card {{ background:#1b1b1b; border:1px solid #333; border-radius:12px; padding:16px; }}
            input, textarea, select {{ width:100%; background:#0f0f0f; color:#fff; border:1px solid #444; border-radius:8px; padding:10px; margin:6px 0 12px; }}
            button {{ background:#d4af37; color:#111; border:none; border-radius:8px; padding:10px 14px; font-weight:700; cursor:pointer; }}
            a {{ color:#d4af37; }}
            pre {{ white-space:pre-wrap; word-break:break-word; background:#0d0d0d; padding:12px; border-radius:8px; }}
            img, video {{ max-width:100%; border-radius:8px; }}
            .assets {{ display:grid; grid-template-columns: repeat(auto-fill, minmax(180px,1fr)); gap:12px; }}
            .muted {{ color:#aaa; font-size:0.95em; }}
            .error {{ border-color:#7a2b2b; background:#231515; }}
          </style>
        </head>
        <body>{body}</body></html>
        """
    )


def run_cli(args: list[str], env_updates: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    if env_updates:
        env.update({k: v for k, v in env_updates.items() if v is not None})
    return subprocess.run(
        ["python3", "-m", "src.main", *args],
        cwd=str(BASE_DIR),
        env=env,
        capture_output=True,
        text=True,
    )


def file_link_item(job_dir: Path, rel: str) -> str | None:
    p = job_dir / rel
    if p.exists():
        return f"<li><a href='file://{p}'>{rel}</a></li>"
    return None


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    jobs = db.get_all_jobs()
    job_items = "".join(
        f"<li><a href='/jobs/{job.job_id}'>{job.job_id}</a> — {html.escape(job.topic)} — {html.escape(job.status)}</li>"
        for job in jobs[:20]
    ) or "<li>No jobs yet.</li>"

    env_path = BASE_DIR / ".env"
    env_text = env_path.read_text(encoding="utf-8") if env_path.exists() else ""
    config_text = (BASE_DIR / "src" / "config.py").read_text(encoding="utf-8")

    body = f"""
    <h1>Stoic Modernized UI</h1>
    <div class='grid'>
      <div class='card'>
        <h2>Start Generation</h2>
        <form method='post' action='/run'>
          <label>Topic</label>
          <input name='topic' value='workplace stress' />
          <label>Video mode</label>
          <select name='video_mode'>
            <option value='short'>short</option>
            <option value='long'>long</option>
          </select>
          <label>Platform preset</label>
          <select name='platform'>
            <option value='auto'>auto</option>
            <option value='youtube'>youtube</option>
            <option value='tiktok'>tiktok</option>
          </select>
          <label>TTS provider</label>
          <select name='provider'>
            <option value='edge'>edge</option>
            <option value='local'>local</option>
            <option value='elevenlabs'>elevenlabs</option>
            <option value='voxcpm'>voxcpm</option>
          </select>
          <label>Skip upload</label>
          <select name='skip_upload'>
            <option value='true'>true</option>
            <option value='false'>false</option>
          </select>
          <button type='submit'>Start full generation</button>
        </form>
      </div>

      <div class='card'>
        <h2>Run Selected Steps</h2>
        <form method='post' action='/steps'>
          <label>Existing job id (leave blank to create from research)</label>
          <input name='job_id' />
          <label>Topic (used when starting from research)</label>
          <input name='topic' value='workplace stress' />
          <label>Video mode</label>
          <select name='video_mode'>
            <option value='short'>short</option>
            <option value='long'>long</option>
          </select>
          <label>Platform preset</label>
          <select name='platform'>
            <option value='auto'>auto</option>
            <option value='youtube'>youtube</option>
            <option value='tiktok'>tiktok</option>
          </select>
          <label>TTS provider</label>
          <select name='provider'>
            <option value='edge'>edge</option>
            <option value='local'>local</option>
            <option value='elevenlabs'>elevenlabs</option>
            <option value='voxcpm'>voxcpm</option>
          </select>
          <label>Comma-separated steps</label>
          <input name='steps' value='research,script,scene,tts,images,subtitles,render,metadata' />
          <button type='submit'>Run selected steps</button>
        </form>
      </div>

      <div class='card'>
        <h2>Environment Variables (.env)</h2>
        <form method='post' action='/save-env'>
          <textarea name='content' rows='16'>{html.escape(env_text)}</textarea>
          <button type='submit'>Save .env</button>
        </form>
      </div>

      <div class='card'>
        <h2>Config File (src/config.py)</h2>
        <form method='post' action='/save-config'>
          <textarea name='content' rows='16'>{html.escape(config_text)}</textarea>
          <button type='submit'>Save config.py</button>
        </form>
      </div>
    </div>

    <div class='card' style='margin-top:20px;'>
      <h2>Jobs</h2>
      <ul>{job_items}</ul>
    </div>
    """
    return html_page("Stoic Modernized UI", body)


@app.post('/run')
def run_full(
    topic: str = Form(...),
    video_mode: str = Form(...),
    platform: str = Form('auto'),
    provider: str = Form(...),
    skip_upload: str = Form(...),
) -> HTMLResponse:
    args = ["run", topic, "--video-mode", video_mode, "--provider", provider]
    if platform != 'auto':
        args += ['--platform', platform]
    if skip_upload == 'true':
        args.append('--skip-upload')
    result = run_cli(args)
    return html_page("Run Result", f"<h1>Run Result</h1><pre>{html.escape(result.stdout)}\n{html.escape(result.stderr)}</pre><p><a href='/'>Back</a></p>")


@app.post('/steps')
def run_steps(
    topic: str = Form(...),
    job_id: str = Form(''),
    video_mode: str = Form(...),
    platform: str = Form('auto'),
    provider: str = Form(...),
    steps: str = Form(...),
) -> HTMLResponse:
    outputs: list[str] = []
    current_job_id = job_id.strip()
    step_list = [step.strip() for step in steps.split(',') if step.strip()]

    for step in step_list:
        if step == 'research':
            args = ["research", topic]
            if current_job_id:
                args += ["--job-id", current_job_id]
            result = run_cli(args)
            outputs.append(f"## research\n{result.stdout}\n{result.stderr}")
            if not current_job_id:
                jobs = db.get_all_jobs()
                if jobs:
                    current_job_id = jobs[0].job_id
        elif step == 'script':
            result = run_cli(["script", current_job_id, "--video-mode", video_mode])
            outputs.append(f"## script\n{result.stdout}\n{result.stderr}")
        elif step == 'scene':
            result = run_cli(["scene", current_job_id])
            outputs.append(f"## scene\n{result.stdout}\n{result.stderr}")
        elif step == 'tts':
            result = run_cli(["tts", current_job_id, "--provider", provider])
            outputs.append(f"## tts\n{result.stdout}\n{result.stderr}")
        elif step == 'images':
            result = run_cli(["images", current_job_id])
            outputs.append(f"## images\n{result.stdout}\n{result.stderr}")
        elif step == 'subtitles':
            result = run_cli(["subtitles", current_job_id])
            outputs.append(f"## subtitles\n{result.stdout}\n{result.stderr}")
        elif step == 'render':
            args = ["render", current_job_id, "--video-mode", video_mode]
            if platform != 'auto':
                args += ['--platform', platform]
            result = run_cli(args)
            outputs.append(f"## render\n{result.stdout}\n{result.stderr}")
        elif step == 'metadata':
            result = run_cli(["metadata", current_job_id])
            outputs.append(f"## metadata\n{result.stdout}\n{result.stderr}")
        elif step == 'upload':
            result = run_cli(["upload", current_job_id])
            outputs.append(f"## upload\n{result.stdout}\n{result.stderr}")

    return html_page("Selected Steps", f"<h1>Selected Steps</h1><pre>{html.escape(chr(10).join(outputs))}</pre><p><a href='/'>Back</a></p>")


@app.post('/save-env')
def save_env(content: str = Form(...)) -> RedirectResponse:
    (BASE_DIR / '.env').write_text(content, encoding='utf-8')
    return RedirectResponse('/', status_code=303)


@app.post('/save-config')
def save_config(content: str = Form(...)) -> RedirectResponse:
    (BASE_DIR / 'src' / 'config.py').write_text(content, encoding='utf-8')
    return RedirectResponse('/', status_code=303)


@app.get('/jobs/{job_id}', response_class=HTMLResponse)
def job_detail(job_id: str) -> HTMLResponse:
    job = db.get_job(job_id)
    if not job:
        return html_page('Job Not Found', f'<h1>Job {job_id} not found</h1><p><a href="/">Back</a></p>')

    job_dir = settings.jobs_dir / job_id
    asset_html = []
    images_dir = job_dir / 'images'
    if images_dir.exists():
        for image in sorted(images_dir.glob('*.jpg')):
            asset_html.append(f"<div><div class='muted'>{html.escape(image.name)}</div><img src='file://{image}' /></div>")

    links: list[str] = []
    for rel in [
        'research/research.json',
        'script/script.json',
        'script/script_generation_report.json',
        'script/local_llm_raw.txt',
        'script/local_llm_parsed.json',
        'script/script_generation_final.json',
        'scenes/scenes.json',
        'subtitles/subtitles.srt',
        'subtitles/subtitles.json',
        'metadata/metadata.json',
        'output/final.mp4',
        'output/thumbnail.jpg',
        f'{job_id}.log',
    ]:
        item = file_link_item(job_dir, rel)
        if item:
            links.append(item)

    report = None
    report_path = job_dir / 'script' / 'script_generation_report.json'
    if report_path.exists():
        try:
            report = load_json(report_path)
        except Exception:
            report = None

    error_card = ''
    if job.error_message or report:
        report_html = ''
        if report:
            report_html = f"""
            <pre>{html.escape(str({
                'local_llm_success': report.get('local_llm_success'),
                'script_generation_succeeded': report.get('script_generation_succeeded'),
                'failure_reason': report.get('failure_reason'),
                'llm_error': report.get('llm_error'),
            }))}</pre>
            """
        error_card = f"""
        <div class='card error' style='margin-top:20px;'>
          <h2>Failure Details</h2>
          <p><strong>Error:</strong> {html.escape(job.error_message or 'No DB error message recorded')}</p>
          {report_html}
        </div>
        """

    assets_list = ''.join(links) or '<li>No files found for this job yet.</li>'

    body = f"""
    <h1>Job {job_id}</h1>
    <p>Status: <strong>{html.escape(job.status)}</strong></p>
    <p>Topic: <strong>{html.escape(job.topic)}</strong></p>
    {error_card}
    <div class='card'>
      <h2>Assets</h2>
      <ul>{assets_list}</ul>
    </div>
    <div class='card' style='margin-top:20px;'>
      <h2>Images</h2>
      <div class='assets'>{''.join(asset_html) or '<p>No images yet.</p>'}</div>
    </div>
    <p style='margin-top:20px;'><a href='/'>Back</a></p>
    """
    return html_page(f"Job {job_id}", body)
