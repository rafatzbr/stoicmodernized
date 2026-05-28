#!/usr/bin/env python3
"""Generate output/social_public/videos.html as a static file explorer."""

from __future__ import annotations

import datetime as dt
import html
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PUBLIC_ROOT = ROOT / "output" / "social_public"
OUTPUT = PUBLIC_ROOT / "videos.html"

HTML_TEMPLATE = """<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>Videos — Stoic Modernized Publisher</title>
  <meta name=\"description\" content=\"Browse public Stoic Modernized media files and generated video directories.\" />
  <style>
    :root{{--bg:#080808;--panel:#121212;--panel2:#181818;--line:#2a2a2a;--text:#f2f2f2;--muted:#a8a8a8;--accent:#d71921;--good:#66c27a}}
    *{{box-sizing:border-box}} body{{margin:0;background:radial-gradient(circle at 22px 22px,rgba(255,255,255,.055) 1px,transparent 1px),var(--bg);background-size:22px 22px;color:var(--text);font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;line-height:1.45}}
    a{{color:inherit}} main{{width:min(1180px,calc(100vw - 28px));margin:0 auto;padding:36px 0 72px}}
    header{{display:flex;justify-content:space-between;gap:20px;align-items:flex-end;border-bottom:1px solid var(--line);padding-bottom:22px;margin-bottom:22px}}
    h1{{font-size:clamp(34px,6vw,72px);line-height:.95;margin:0;letter-spacing:-.06em}} .eyebrow,.mono{{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}} .eyebrow{{font-size:12px;text-transform:uppercase;letter-spacing:.12em;color:var(--muted);margin-bottom:8px}} .muted{{color:var(--muted)}}
    .toplinks{{display:flex;gap:10px;flex-wrap:wrap;justify-content:flex-end}} .button{{min-height:38px;border:1px solid var(--line);padding:0 13px;display:inline-flex;align-items:center;text-decoration:none;font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:12px;text-transform:uppercase;letter-spacing:.08em;background:rgba(18,18,18,.7)}} .button:hover{{border-color:var(--text)}}
    .bar{{display:grid;grid-template-columns:1fr auto;gap:12px;margin:18px 0}} input{{width:100%;min-height:44px;background:var(--panel);border:1px solid var(--line);color:var(--text);padding:0 14px;font-size:15px}} input:focus{{outline:1px solid var(--accent);border-color:var(--accent)}}
    .crumbs{{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin:18px 0;color:var(--muted)}} .crumbs a{{text-decoration:none;border:1px solid var(--line);padding:6px 10px;background:rgba(18,18,18,.8)}} .crumbs a:hover{{border-color:var(--text);color:var(--text)}}
    .summary{{display:flex;gap:18px;flex-wrap:wrap;color:var(--muted);font-size:14px;margin-bottom:14px}} .summary b{{color:var(--text)}}
    .list{{border:1px solid var(--line);background:rgba(12,12,12,.8)}} .row{{display:grid;grid-template-columns:minmax(220px,1fr) 130px 210px 98px;gap:14px;align-items:center;padding:14px 16px;border-bottom:1px solid var(--line);text-decoration:none}} .row:last-child{{border-bottom:0}} .row:hover{{background:var(--panel2)}} .head{{color:var(--muted);font-size:12px;text-transform:uppercase;letter-spacing:.1em;background:#0d0d0d}} .sort{{appearance:none;background:transparent;border:0;color:inherit;padding:0;font:inherit;text-transform:inherit;letter-spacing:inherit;cursor:pointer;text-align:left}} .sort:hover,.sort:focus{{color:var(--text);outline:0}} .sort .arrow{{display:inline-block;min-width:1em;color:var(--accent)}} .name{{display:flex;align-items:center;gap:10px;min-width:0}} .icon{{width:28px;height:28px;display:inline-flex;align-items:center;justify-content:center;border:1px solid var(--line);background:var(--panel);flex:0 0 auto}} .name-text{{min-width:0}} .label{{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}} .sub{{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--muted);font-size:12px;margin-top:2px}} .kind,.date,.size{{color:var(--muted);font-size:14px}} .empty{{padding:42px;text-align:center;color:var(--muted)}}
    .footer{{margin-top:22px;color:var(--muted);font-size:13px}} .accent{{color:var(--accent)}}
    @media(max-width:760px){{header{{display:block}}.toplinks{{justify-content:flex-start;margin-top:18px}}.bar{{grid-template-columns:1fr}}.row{{grid-template-columns:1fr;gap:6px}}.head{{display:none}}.kind:before{{content:'Type: ';color:#777}}.size:before{{content:'Size: ';color:#777}}.date:before{{content:'Modified: ';color:#777}}}}
  </style>
</head>
<body>
  <main>
    <header>
      <div>
        <div class=\"eyebrow\">Stoic Modernized public media</div>
        <h1>Videos<span class=\"accent\">.</span></h1>
        <div class=\"muted\">Browse generated media directories and files served from <span class=\"mono\">media.zweb.ca</span>.</div>
      </div>
      <nav class=\"toplinks\" aria-label=\"Site links\">
        <a class=\"button\" href=\"/\">Home</a>
        <a class=\"button\" href=\"/privacy/\">Privacy</a>
        <a class=\"button\" href=\"/terms/\">Terms</a>
      </nav>
    </header>
    <div class=\"bar\"><input id=\"search\" type=\"search\" placeholder=\"Filter current folder…\" autocomplete=\"off\" /><a class=\"button\" id=\"downloadCurrent\" href=\"/\">Open Folder URL</a></div>
    <nav class=\"crumbs\" id=\"crumbs\" aria-label=\"Breadcrumbs\"></nav><div class=\"summary\" id=\"summary\"></div>
    <section class=\"list\" aria-label=\"File explorer\"><div class=\"row head\"><div><button class=\"sort\" type=\"button\" data-sort=\"name\">Name <span class=\"arrow\" id=\"sortName\">↑</span></button></div><div>Type</div><div><button class=\"sort\" type=\"button\" data-sort=\"modified\">Modified <span class=\"arrow\" id=\"sortModified\"></span></button></div><div>Size</div></div><div id=\"rows\"></div></section>
    <div class=\"footer\">Generated from the server-side file tree. Refresh this page after new social-public files are staged.</div>
  </main>
  <script id=\"tree-data\" type=\"application/json\">{tree_json}</script>
  <script>
    const tree = JSON.parse(document.getElementById('tree-data').textContent); const rows = document.getElementById('rows'); const crumbs = document.getElementById('crumbs'); const summary = document.getElementById('summary'); const search = document.getElementById('search'); const openFolder = document.getElementById('downloadCurrent'); const sortButtons = document.querySelectorAll('[data-sort]');
    let sortKey = 'modified'; let sortDir = 'desc';
    function fmtSize(bytes) {{ if (bytes === null || bytes === undefined) return '—'; const units = ['B','KB','MB','GB']; let n = bytes; let i = 0; while (n >= 1024 && i < units.length - 1) {{ n /= 1024; i++; }} return `${{n.toFixed(i ? 1 : 0)}} ${{units[i]}}`; }}
    function fmtDate(iso) {{ return new Date(iso).toLocaleString(undefined, {{year:'numeric', month:'short', day:'2-digit', hour:'2-digit', minute:'2-digit'}}); }}
    function currentPath() {{ return decodeURIComponent((location.hash || '#/').slice(1)).replace(/^[/]/,'').replace(/[/]$/,''); }}
    function findNode(path) {{ if (!path) return tree; return path.split('/').filter(Boolean).reduce((node, part) => (node.children || []).find(c => c.name === part), tree) || tree; }}
    function hasIndexPage(item) {{ return item.type === 'directory' && (item.children || []).some(child => child.type === 'file' && child.name.toLowerCase() === 'index.html'); }}
    function hrefFor(item) {{ if (hasIndexPage(item)) return '/' + item.path.replace(/[/]$/,'') + '/index.html'; return item.type === 'directory' ? '#/' + item.path : '/' + item.path; }}
    function targetAttrs(item) {{ return item.type === 'file' || hasIndexPage(item) ? 'target=\"_blank\" rel=\"noopener\"' : ''; }}
    function escapeHtml(value) {{ return String(value).replace(/[&<>\"']/g, c => ({{'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',"'":'&#39;'}}[c])); }}
    function renderCrumbs(path) {{ const parts = path ? path.split('/') : []; let acc = ''; crumbs.innerHTML = `<a href=\"#/\">videos</a>` + parts.map(part => {{ acc = acc ? acc + '/' + part : part; return `<span>/</span><a href=\"#/${{encodeURI(acc)}}\">${{escapeHtml(part)}}</a>`; }}).join(''); }}
    function fileIcon(name) {{ const n = name.toLowerCase(); if (n.endsWith('.mp4')) return '🎬'; if (n.endsWith('.jpg')||n.endsWith('.png')||n.endsWith('.webp')) return '🖼️'; if (n.endsWith('.html')) return '🌐'; if (n.endsWith('.json')) return '🧾'; return '📄'; }}
    function displayName(item) {{ return item.title || item.name; }}
    function sortValue(item) {{ if (sortKey === 'modified') return new Date(item.modified).getTime() || 0; return displayName(item).toLowerCase(); }}
    function sortedChildren(children) {{ const direction = sortDir === 'asc' ? 1 : -1; return [...children].sort((a, b) => {{ if (a.type !== b.type) return a.type === 'directory' ? -1 : 1; const av = sortValue(a); const bv = sortValue(b); if (av < bv) return -1 * direction; if (av > bv) return 1 * direction; return a.name.localeCompare(b.name); }}); }}
    function updateSortIndicators() {{ document.getElementById('sortName').textContent = sortKey === 'name' ? (sortDir === 'asc' ? '↑' : '↓') : ''; document.getElementById('sortModified').textContent = sortKey === 'modified' ? (sortDir === 'asc' ? '↑' : '↓') : ''; }}
    function matchesQuery(item, q) {{ if (!q) return true; return [item.name, item.title, item.path].filter(Boolean).some(value => value.toLowerCase().includes(q)); }}
    function render() {{ const node = findNode(currentPath()); const q = search.value.trim().toLowerCase(); renderCrumbs(node.path || ''); openFolder.href = node.path ? '/' + node.path + '/' : '/'; const children = sortedChildren((node.children || []).filter(item => matchesQuery(item, q))); const dirs = children.filter(i => i.type === 'directory').length; const files = children.length - dirs; updateSortIndicators(); summary.innerHTML = `<span><b>${{dirs}}</b> directories</span><span><b>${{files}}</b> files</span><span>Current: <b class=\"mono\">/${{escapeHtml(node.path || '')}}</b></span>`; if (!children.length) {{ rows.innerHTML = '<div class=\"empty\">No files match this filter.</div>'; return; }} rows.innerHTML = children.map(item => `<a class=\"row\" href=\"${{hrefFor(item)}}\" ${{targetAttrs(item)}}><div class=\"name\"><span class=\"icon\">${{item.type === 'directory' ? '📁' : fileIcon(item.name)}}</span><span class=\"name-text\"><span class=\"label\">${{escapeHtml(displayName(item))}}</span>${{item.title ? `<span class=\"sub mono\">${{escapeHtml(item.name)}}</span>` : ''}}</span></div><div class=\"kind\">${{item.type}}</div><div class=\"date\">${{fmtDate(item.modified)}}</div><div class=\"size\">${{fmtSize(item.size)}}</div></a>`).join(''); }}
    sortButtons.forEach(button => button.addEventListener('click', () => {{ const key = button.dataset.sort; if (sortKey === key) {{ sortDir = sortDir === 'asc' ? 'desc' : 'asc'; }} else {{ sortKey = key; sortDir = key === 'modified' ? 'desc' : 'asc'; }} render(); }}));
    addEventListener('hashchange', () => {{ search.value = ''; render(); }}); search.addEventListener('input', render); render();
  </script>
</body>
</html>
"""


def title_for_directory(path: Path) -> str | None:
    """Return the human video title from a per-job helper page, when present."""
    index_path = path / "index.html"
    if not index_path.exists():
        return None
    try:
        text = index_path.read_text(encoding="utf-8")
    except OSError:
        return None
    match = re.search(r'<div[^>]+id=["\']title["\'][^>]*>(.*?)</div>', text, flags=re.IGNORECASE | re.DOTALL)
    if not match:
        return None
    title = re.sub(r"<[^>]+>", "", match.group(1)).strip()
    return html.unescape(title) or None


def node_for(path: Path, public_root: Path = PUBLIC_ROOT, inherited_title: str | None = None) -> dict:
    stat = path.stat()
    rel = path.relative_to(public_root).as_posix() if path != public_root else ""
    item: dict = {
        "name": path.name if path != public_root else "videos",
        "path": rel,
        "type": "directory" if path.is_dir() else "file",
        "size": stat.st_size if path.is_file() else None,
        "modified": dt.datetime.fromtimestamp(stat.st_mtime, tz=dt.UTC).isoformat(timespec="seconds"),
        "url": f"/{rel}" if rel else "/",
    }
    if inherited_title and path.is_file() and path.suffix.lower() == ".mp4":
        item["title"] = inherited_title
    if path.is_dir():
        title = title_for_directory(path) or inherited_title
        if title:
            item["title"] = title
        item["children"] = [
            node_for(child, public_root=public_root, inherited_title=title)
            for child in sorted(path.iterdir(), key=lambda candidate: (not candidate.is_dir(), candidate.name.lower()))
            if child.name != ".DS_Store"
        ]
    return item


def generate_explorer(public_root: Path = PUBLIC_ROOT, output: Path | None = None) -> Path:
    public_root.mkdir(parents=True, exist_ok=True)
    output = output or public_root / "videos.html"
    tree_json = json.dumps(node_for(public_root, public_root=public_root), separators=(",", ":"), ensure_ascii=False).replace("</", "<\\/")
    output.write_text(HTML_TEMPLATE.format(tree_json=tree_json), encoding="utf-8")
    return output


def main() -> None:
    print(generate_explorer(PUBLIC_ROOT, OUTPUT))


if __name__ == "__main__":
    main()
