"""Ledger-generated channel strategy and per-job steering packets."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
import re

from src.config import Channel, VideoMode
from src.stages.upload import BLOCKED_TOPIC_KEYWORDS
from src.utils import load_json, save_json


DISCOVERY_KEYWORDS = {
    "meeting",
    "meetings",
    "slack",
    "notification",
    "notifications",
    "burnout",
    "procrastination",
    "deadline",
    "deadlines",
    "layoff",
    "layoffs",
    "focus",
    "urgent",
    "urgency",
    "office",
    "boss",
    "coworker",
    "coworkers",
}

CONVERSION_KEYWORDS = {
    "anxiety",
    "fear",
    "control",
    "calm",
    "identity",
    "dignity",
    "acceptance",
    "approval",
    "self-command",
    "self command",
    "understood",
    "understand you",
    "like you",
    "worth",
}

SUBJECT_UMBRELLA_TRIGGER_MAP: dict[str, tuple[str, tuple[str, ...]]] = {
    "attention_distraction": ("attention/distraction", ("phone", "notification", "inbox", "tab", "focus", "calendar block")),
    "fatigue_boundaries": ("fatigue/boundaries", ("calendar", "white space", "weekend", "energy", "boundary", "overcommit")),
    "loss_of_control": ("loss of control", ("dashboard", "filter", "export", "timestamp", "version", "source", "date range", "password", "build", "printer", "broken", "budget")),
    "uncertainty_waiting": ("uncertainty/waiting", ("approval", "pending", "waiting", "handoff", "owner", "decision", "clarifying", "queue")),
    "desire_ambition": ("desire/ambition", ("promotion", "raise", "metrics", "recognition", "status", "ambition")),
    "ego_reputation": ("ego/reputation", ("review", "comment", "feedback", "criticism", "personal", "corrected", "decision record")),
    "conflict_friction": ("conflict/friction", ("boss", "coworker", "client", "meeting", "disagreement", "disrespect")),
    "everyday_inconvenience": ("everyday inconvenience", ("coffee", "elevator", "parking", "lunch", "printer jam", "noise")),
}

OPERATIONAL_TRIGGER_PATTERNS: tuple[tuple[str, str, list[str]], ...] = (
    ("dashboard filter", "loss_of_control", ["dashboard", "filter", "data quality"]),
    ("source date range", "loss_of_control", ["source", "date range", "scope"]),
    ("export timestamp", "loss_of_control", ["export", "timestamp", "stale data"]),
    ("version label", "loss_of_control", ["version", "label", "file"]),
    ("budget line", "loss_of_control", ["budget", "scope", "resource constraint"]),
    ("approval queue", "uncertainty_waiting", ["approval", "queue", "waiting"]),
    ("handoff owner", "uncertainty_waiting", ["handoff", "owner", "next action"]),
    ("decision record", "ego_reputation", ["decision record", "audit trail", "memory"]),
    ("review comment", "ego_reputation", ["review", "comment", "feedback"]),
    ("calendar block", "attention_distraction", ["calendar", "focus block", "interruption"]),
    ("checklist step", "attention_distraction", ["checklist", "step", "verification"]),
    ("promotion window", "desire_ambition", ["promotion", "ambition", "next action"]),
    ("status game", "desire_ambition", ["status", "approval", "recognition"]),
    ("discipline system", "fatigue_boundaries", ["discipline", "boundary", "energy"]),
    ("printer jam", "everyday_inconvenience", ["printer", "jam", "office equipment"]),
)


@dataclass
class LedgerStrategyManager:

    project_root: Path | None = None
    workspace_root: Path | None = None

    def __post_init__(self) -> None:
        self.project_root = self.project_root or Path(__file__).resolve().parent.parent
        self.workspace_root = self.workspace_root or (Path.home() / ".openclaw" / "workspace")
        self.state_dir = self.project_root / "state"
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.artifacts_dir = self.workspace_root / "artifacts"
        self.global_strategy_path = self.state_dir / "ledger_strategy.json"
        self.topic_ideas_path = self.state_dir / "ledger_topic_ideas.json"
        self.topic_plan_path = self.state_dir / "ledger_topic_plan.json"

    def _artifact_candidates(self) -> list[Path]:
        candidates: list[Path] = []
        for pattern in (
            "stoic-modernized-council-plan-*.md",
            "stoic-modernized-youtube-analytics-*.md",
            "stoic-modernized-youtube-metrics-*.md",
            "stoic-modernized-youtube-analytics-snapshot-*.json",
            "stoic-modernized-facebook-metrics-*.md",
            "stoic-modernized-facebook-analytics-*.md",
            "stoic-modernized-facebook-analytics-snapshot-*.json",
            "stoic-modernized-tiktok-analytics-*.md",
            "stoic-modernized-tiktok-metrics-*.md",
            "stoic-modernized-tiktok-analytics-*.json",
            "stoic-modernized-tiktok-metrics-*.json",
            "stoic-modernized-tiktok-analytics-*.csv",
            "stoic-modernized-tiktok-metrics-*.csv",
        ):
            matches = sorted(self.artifacts_dir.glob(pattern))
            if matches:
                candidates.append(matches[-1])
        return candidates

    def _extract_useful_lines(self, text: str, max_lines: int = 40) -> list[str]:
        lines: list[str] = []
        for raw in text.splitlines():
            line = raw.strip()
            if not line:
                continue
            if line.startswith("#") or line.startswith("- ") or re.match(r"^\d+\.\s", line):
                lines.append(line)
            if len(lines) >= max_lines:
                break
        return lines

    def _read_metric_artifacts(self) -> tuple[list[str], list[str], dict[str, str]]:
        source_files: list[str] = []
        snippets: list[str] = []
        texts: dict[str, str] = {}
        for path in self._artifact_candidates():
            source_files.append(str(path))
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            texts[str(path)] = text
            snippets.extend(self._extract_useful_lines(text, max_lines=20))
        return source_files, snippets, texts

    @staticmethod
    def _first_number(pattern: str, text: str) -> float | None:
        match = re.search(pattern, text, flags=re.IGNORECASE | re.MULTILINE)
        if not match:
            return None
        raw = match.group(1).replace(",", "")
        try:
            return float(raw)
        except ValueError:
            return None

    @staticmethod
    def _slug_tokens(value: str) -> set[str]:
        stop = {"the", "and", "your", "you", "with", "without", "work", "workplace", "stoic", "stoicism", "how", "why", "what", "when", "from", "that", "this"}
        return {token for token in re.findall(r"[a-z][a-z-]+", value.lower()) if token not in stop and len(token) > 3}

    def _extract_ranked_titles(self, text: str, *, max_items: int = 5) -> list[str]:
        titles: list[str] = []
        for raw in text.splitlines():
            line = raw.strip()
            match = re.match(r"^\d+\.\s+(.+?)(?:\s+[-–]\s+|$)", line)
            if match:
                title = match.group(1).strip().strip('"')
                if title and not title.lower().startswith(("video id", "views")):
                    titles.append(title)
            if len(titles) >= max_items:
                break
        return titles

    def _infer_themes_from_titles(self, titles: list[str]) -> list[str]:
        theme_map = {
            "conflict": {"coworker", "coworkers", "colleague", "disrespect", "react", "status"},
            "strategic patience": {"patience", "leverage", "timing", "wait", "power"},
            "discipline systems": {"discipline", "focus", "friction", "willpower", "overexplaining"},
            "meetings": {"meeting", "meetings"},
            "control": {"control", "outcome", "outcomes"},
            "anxiety": {"anxiety", "worry", "dread", "stress"},
        }
        scores: dict[str, int] = {key: 0 for key in theme_map}
        for title in titles:
            tokens = self._slug_tokens(title)
            for theme, keywords in theme_map.items():
                scores[theme] += len(tokens & keywords)
        ranked = [theme for theme, score in sorted(scores.items(), key=lambda item: item[1], reverse=True) if score > 0]
        return ranked[:5]

    def _extract_tiktok_weightings(self, texts: dict[str, str]) -> list[dict[str, Any]]:
        combined = "\n".join(text for path, text in texts.items() if "tiktok" in path.lower())
        weightings: list[dict[str, Any]] = []
        for match in re.finditer(r"-\s*(\d+(?:\.\d+)?)%\s+([^\n]+)", combined, flags=re.IGNORECASE):
            label = match.group(2).strip().rstrip(".")
            weightings.append({"label": label, "weight": float(match.group(1))})
        return weightings

    def _derive_metric_signals(self, texts: dict[str, str]) -> dict[str, Any]:
        youtube_text = "\n".join(text for path, text in texts.items() if "youtube" in path.lower())
        facebook_text = "\n".join(text for path, text in texts.items() if "facebook" in path.lower())
        tiktok_text = "\n".join(text for path, text in texts.items() if "tiktok" in path.lower())
        shorts_views = self._first_number(r"SHORTS:\s*([\d,]+)\s+views", youtube_text)
        search_minutes = self._first_number(r"YT_SEARCH:\s*[\d,]+\s+views,\s*([\d,]+)\s+minutes", youtube_text)
        mobile_views = self._first_number(r"^\s*-?\s*MOBILE:\s*([\d,]+)\s+views", youtube_text)
        desktop_views = self._first_number(r"^\s*-?\s*DESKTOP:\s*([\d,]+)\s+views", youtube_text)
        unsub_views = self._first_number(r"^\s*-?\s*UNSUBSCRIBED:\s*([\d,]+)\s+views", youtube_text)
        sub_views = self._first_number(r"^\s*-?\s*SUBSCRIBED:\s*([\d,]+)\s+views", youtube_text)
        subscribers_gained = self._first_number(r"Subscribers gained:\s*([\d,]+)", youtube_text)
        facebook_video_views = self._first_number(r"Page video views:\s*([\d,]+)", facebook_text)
        facebook_engagements = self._first_number(r"Page post engagements:\s*([\d,]+)", facebook_text)
        facebook_reach = self._first_number(r"Page unique impressions/reach:\s*([\d,]+)", facebook_text)
        youtube_titles = self._extract_ranked_titles(youtube_text)
        facebook_titles = self._extract_ranked_titles(facebook_text)
        tiktok_titles = self._extract_ranked_titles(tiktok_text)
        tiktok_weights = self._extract_tiktok_weightings(texts)

        platform = {
            "youtube_shorts_views": shorts_views,
            "youtube_search_minutes": search_minutes,
            "mobile_view_share": None,
            "unsubscribed_view_share": None,
            "subscribers_gained": subscribers_gained,
            "facebook_video_views": facebook_video_views,
            "facebook_post_engagements": facebook_engagements,
            "facebook_reach": facebook_reach,
        }
        if mobile_views is not None and desktop_views is not None and mobile_views + desktop_views > 0:
            platform["mobile_view_share"] = round(mobile_views / (mobile_views + desktop_views), 3)
        if unsub_views is not None and sub_views is not None and unsub_views + sub_views > 0:
            platform["unsubscribed_view_share"] = round(unsub_views / (unsub_views + sub_views), 3)

        winning_themes = []
        for item in tiktok_weights:
            winning_themes.append(item["label"])
        winning_themes.extend(self._infer_themes_from_titles(tiktok_titles + facebook_titles + youtube_titles))
        deduped_themes: list[str] = []
        for theme in winning_themes:
            normalized = theme.lower().strip()
            if normalized and normalized not in deduped_themes:
                deduped_themes.append(normalized)

        format_steering = [
            "mobile-first 9:16 Shorts framing",
            "name the concrete work scenario in the first 1-2 seconds",
            "keep one problem, one Stoic move, one concrete scenario",
        ]
        if platform["unsubscribed_view_share"] and platform["unsubscribed_view_share"] >= 0.8:
            format_steering.append("optimize for cold/unsubscribed viewers: self-contained hook before channel context")
        if tiktok_weights:
            format_steering.append("for TikTok reuse, prefer scenario-first captions and 2-4 focused hashtags")
        if facebook_text:
            format_steering.append("join Facebook Reels/Page metrics with YouTube and TikTok before choosing the next content batch")

        return {
            "source_count": len(texts),
            "platform": platform,
            "winning_themes": deduped_themes[:8],
            "youtube_top_titles": youtube_titles[:5],
            "facebook_top_titles": facebook_titles[:5],
            "tiktok_top_titles": tiktok_titles[:5],
            "tiktok_weightings": tiktok_weights,
            "format_steering": format_steering,
            "manual_tiktok_supported_patterns": [
                "stoic-modernized-tiktok-analytics-YYYY-MM-DD.md/json/csv",
                "stoic-modernized-tiktok-metrics-YYYY-MM-DD.md/json/csv",
            ],
            "facebook_supported_patterns": [
                "stoic-modernized-facebook-metrics-YYYY-MM-DD.md",
                "stoic-modernized-facebook-analytics-YYYY-MM-DD.md",
                "stoic-modernized-facebook-analytics-snapshot-YYYY-MM-DD.json",
            ],
        }

    def _steered_strategy_defaults(self, metric_signals: dict[str, Any]) -> dict[str, Any]:
        winning = metric_signals.get("winning_themes") or []
        tiktok_weights = metric_signals.get("tiktok_weightings") or []
        discovery_share, conversion_share, balanced_share = 5, 2, 3
        if tiktok_weights:
            discovery_share, conversion_share, balanced_share = 6, 2, 2
        platform = metric_signals.get("platform") or {}
        if (platform.get("subscribers_gained") or 0) <= 2 and (platform.get("unsubscribed_view_share") or 0) >= 0.8:
            conversion_share = max(conversion_share, 3)
            discovery_share = max(discovery_share - 1, 4)

        preferred = [
            "coworker disrespect",
            "status games",
            "strategic patience",
            "discipline systems",
            "overexplaining",
            "meetings",
            "focus friction",
            "burnout tied to control",
        ]
        for theme in reversed(winning):
            if theme and theme not in preferred:
                preferred.insert(0, theme)
        return {
            "shares": {"discovery": discovery_share, "conversion": conversion_share, "balanced": balanced_share},
            "preferred_scenarios": preferred[:14],
        }

    def generate_global_strategy(self) -> dict[str, Any]:
        source_files, snippets, artifact_texts = self._read_metric_artifacts()
        metric_signals = self._derive_metric_signals(artifact_texts)
        steered_defaults = self._steered_strategy_defaults(metric_signals)

        strategy = {
            "generated_at": datetime.now(UTC).isoformat(),
            "source_files": source_files,
            "evidence_excerpt": snippets[:50],
            "metric_signals": metric_signals,
            "format_steering": metric_signals.get("format_steering", []),
            "distribution": {
                "primary_surface": "shorts_feed",
                "device_priority": "mobile_first",
                "audience_profile": "mostly_unsubscribed",
                "secondary_surface": "linkedin_experiment",
                "tiktok_surface": "scenario_first_short_hooks",
            },
            "content_lanes": {
                "discovery": {
                    "share": steered_defaults["shares"]["discovery"],
                    "themes": [
                        "conflict",
                        "disrespect",
                        "patience",
                        "discipline",
                        "focus",
                        "decision-making",
                        "overexplaining",
                        "burnout",
                        "procrastination",
                        "meetings",
                        "power dynamics",
                        "status games",
                    ],
                    "title_formulas": [
                        "Stop <bad loop> at work",
                        "How to <solve work pain> without <common trap>",
                        "Your <workplace trigger> only wins if you react",
                        "<Stoic move> is the workplace power move nobody teaches",
                        "What Marcus Aurelius would do in <specific work scenario>",
                    ],
                },
                "conversion": {
                    "share": steered_defaults["shares"]["conversion"],
                    "themes": [
                        "anxiety",
                        "control",
                        "calm",
                        "dignity",
                        "self-command",
                        "acceptance",
                    ],
                    "title_formulas": [
                        "Why <inner struggle> keeps running your work life",
                        "You do not need <false need> to stay steady",
                        "Calm is not <misbelief> — it is <reframe>",
                    ],
                },
                "balanced": {
                    "share": steered_defaults["shares"]["balanced"],
                    "themes": [
                        "patience",
                        "focus",
                        "calm",
                        "decision-making",
                        "timing",
                        "restraint",
                        "clarity",
                    ],
                    "title_formulas": [
                        "Why <work pressure> gets worse when you rush",
                        "How to stay steady when work feels urgent",
                        "<Stoic move> beats reacting under pressure",
                    ],
                },
            },
            "title_avoid": [
                "abstract philosophy without a modern work scenario",
                "airy words like boredom or letting go without tension",
                "subtitle-style short titles with colons or parentheses",
            ],
            "hook_constraints": [
                "name the work problem in the first 1-2 seconds",
                "use plain language, not mystical Stoic prose",
                "match the script angle exactly",
            ],
            "script_constraints": [
                "one problem, one Stoic move, one concrete scenario",
                "55-70 seconds for most shorts",
                "prefer practical phrasing over slogans",
            ],
            "research_steering": {
                "prioritize_scenarios": steered_defaults["preferred_scenarios"],
                "prioritize_emotions": [
                    "reactivity",
                    "resentment",
                    "loss of control",
                    "humiliation",
                    "approval seeking",
                    "fear",
                    "anxiety",
                ],
                "deprioritize_topics": [
                    "generic anxiety without a concrete scenario",
                    "slack-specific or brand-specific hooks",
                    "broad rest or stillness advice without tension",
                ],
                "avoid_angles": [
                    "generic philosophy surveys",
                    "detached inspirational content",
                    "multiple unrelated Stoic ideas in one short",
                ],
            },
            "platform_packaging": {
                "youtube": {
                    "caption_style": "longer metadata allowed",
                    "hashtags": "3-6 relevant hashtags",
                    "affiliate_links": True,
                    "description_style": "hook + CTA + resources",
                },
                "tiktok": {
                    "caption_style": "one sharp hook sentence, no paragraph dump",
                    "hashtags": "2-4 scenario-specific hashtags",
                    "affiliate_links": False,
                    "description_style": "no resource block, no long CTA, no YouTube-style description inheritance",
                    "winning_topics": [
                        "coworker disrespect",
                        "strategic patience",
                        "discipline and focus systems",
                        "burnout from control",
                        "status games",
                        "overexplaining",
                    ],
                    "avoid_topics": [
                        "boredom",
                        "stillness",
                        "generic rest advice",
                        "broad abstract philosophy",
                        "generic anxiety without tension",
                    ],
                },
            },
            "active_experiments": [
                {
                    "tag": "discovery_batch",
                    "goal": "increase shorts-feed reach with concrete workplace framing",
                    "success_metric": "average 24h views per video",
                },
                {
                    "tag": "tiktok_conflict_batch",
                    "goal": "test conflict/disrespect and patience hooks on TikTok",
                    "success_metric": "average TikTok views and shares per post",
                },
                {
                    "tag": "conversion_batch",
                    "goal": "increase subscribers gained per video with identity/emotion framing",
                    "success_metric": "subscribers gained per video",
                },
                {
                    "tag": "linkedin_repost",
                    "goal": "test LinkedIn as repeatable external surface",
                    "success_metric": "external views and linkedin source detail",
                },
            ],
        }
        save_json(strategy, self.global_strategy_path)
        return strategy

    def load_global_strategy(self) -> dict[str, Any]:
        candidates = self._artifact_candidates()
        if self.global_strategy_path.exists():
            latest_artifact_mtime = max((path.stat().st_mtime for path in candidates), default=0)
            if latest_artifact_mtime <= self.global_strategy_path.stat().st_mtime:
                payload = load_json(self.global_strategy_path)
                if isinstance(payload, dict):
                    return payload
        return self.generate_global_strategy()

    def _classify_objective(self, topic: str, strategy: dict[str, Any]) -> str:
        lowered = topic.lower()
        if any(keyword in lowered for keyword in CONVERSION_KEYWORDS):
            return "conversion"
        if any(keyword in lowered for keyword in DISCOVERY_KEYWORDS):
            return "discovery"
        return "balanced"

    def _objective_themes(self, strategy: dict[str, Any], objective: str) -> list[str]:
        if objective == "conversion":
            return list(strategy["content_lanes"]["conversion"]["themes"])
        if objective == "discovery":
            return list(strategy["content_lanes"]["discovery"]["themes"])
        return list(strategy["content_lanes"]["balanced"]["themes"])

    def _filter_blocked_terms(self, values: list[str], topic: str) -> list[str]:
        lowered_topic = topic.lower()
        filtered: list[str] = []
        for value in values:
            lowered_value = value.lower()
            if any(blocked in lowered_value and blocked not in lowered_topic for blocked in BLOCKED_TOPIC_KEYWORDS):
                continue
            filtered.append(value)
        return filtered

    def build_job_packet(
        self,
        job_id: str,
        topic: str,
        channel: Channel,
        video_mode: VideoMode,
    ) -> dict[str, Any]:
        strategy = self.load_global_strategy()
        objective = self._classify_objective(topic, strategy)
        themes = self._objective_themes(strategy, objective)
        lane_key = objective if objective in ("discovery", "conversion", "balanced") else "balanced"
        title_formulas = self._filter_blocked_terms(list(strategy["content_lanes"][lane_key]["title_formulas"]), topic)
        themes = self._filter_blocked_terms(themes, topic)
        packet = {
            "generated_at": datetime.now(UTC).isoformat(),
            "job_id": job_id,
            "topic": topic,
            "channel": channel.value,
            "video_mode": video_mode.value,
            "objective": objective,
            "batch_lane": lane_key,
            "target_viewer_state": {
                "discovery": "busy worker with a concrete problem",
                "conversion": "viewer who recognizes themselves in the struggle",
                "balanced": "worker who wants both practical relief and emotional steadiness",
            }[objective],
            "recommended_angle": (
                f"Tie '{topic}' to a modern work scenario and a single Stoic move. "
                f"Bias toward {objective} outcomes without drifting into generic philosophy."
            ),
            "packaging_angle": {
                "discovery": "concrete workplace pain first, Stoic relief second",
                "conversion": "identity-level emotional struggle first, Stoic reframe second",
                "balanced": "concrete workplace pain with an inner-state payoff",
            }[objective],
            "title_formulas": title_formulas,
            "research_steering": {
                "themes": themes,
                "preferred_queries": [
                    f'"{topic}" workplace stoic',
                    f'"{topic}" work anxiety focus burnout',
                    f'"{topic}" site:hbr.org OR site:psychologytoday.com OR site:calnewport.com',
                ],
                "required_evidence": [
                    "one concrete work scenario",
                    "one specific emotional or behavioral pattern",
                    "one Stoic move that can be applied immediately",
                ],
                "avoid_angles": list(strategy["research_steering"]["avoid_angles"]),
            },
            "title_constraints": list(strategy["hook_constraints"][:1]) + list(title_formulas[:2]),
            "hook_constraints": list(strategy["hook_constraints"]),
            "script_constraints": list(strategy["script_constraints"]),
            "cta_style": "subscribe-only CTA; never promise to send viewers resources" if objective != "discovery" else "light subscribe CTA without resource promises",
            "distribution_notes": [
                "mobile-first captions and framing",
                "shorts-feed hook matters more than SEO",
                "consider LinkedIn repost if topic is strongly workplace-relevant",
                "for TikTok, prefer scenario-first hooks and do not inherit YouTube resource-heavy captions",
                *list(strategy.get("format_steering", [])),
            ],
            "avoid_angles": list(strategy["research_steering"]["avoid_angles"]),
            "experiment_tag": {
                "discovery": "discovery_batch",
                "conversion": "conversion_batch",
                "balanced": "balanced_batch",
            }[objective],
            "experiment_hypothesis": {
                "discovery": "A concrete work-problem hook will improve shorts-feed reach.",
                "conversion": "An identity/emotion hook will improve subscriber conversion.",
                "balanced": "A concrete work problem plus inner-state payoff will balance reach and conversion.",
            }[objective],
            "script_goal": "Deliver one work scenario, one emotional pattern, and one Stoic move with scene-ready specificity.",
            "metric_signals": strategy.get("metric_signals", {}),
            "format_steering": strategy.get("format_steering", []),
            "strategy_source_files": strategy.get("source_files", []),
        }
        strategy_dir = self.project_root / "output" / "jobs" / job_id / "strategy"
        strategy_dir.mkdir(parents=True, exist_ok=True)
        save_json(packet, strategy_dir / "ledger_packet.json")
        return packet

    def load_job_packet(self, job_id: str) -> dict[str, Any] | None:
        path = self.project_root / "output" / "jobs" / job_id / "strategy" / "ledger_packet.json"
        if not path.exists():
            return None
        payload = load_json(path)
        return payload if isinstance(payload, dict) else None

    def ensure_job_packet(
        self,
        job_id: str,
        topic: str,
        channel: Channel,
        video_mode: VideoMode,
    ) -> dict[str, Any]:
        existing = self.load_job_packet(job_id)
        if existing:
            return existing
        return self.build_job_packet(job_id, topic, channel, video_mode)

    def _topic_variety_metadata(self, title: str, angle: str = "") -> dict[str, Any]:
        text = f"{title} {angle}".lower()
        for trigger, umbrella, family in OPERATIONAL_TRIGGER_PATTERNS:
            if all(part in text for part in trigger.split()):
                return {
                    "subject_umbrella": umbrella,
                    "operational_trigger": trigger,
                    "subject_family": family,
                }
        for umbrella, (_label, tokens) in SUBJECT_UMBRELLA_TRIGGER_MAP.items():
            matches = [token for token in tokens if token in text]
            if matches:
                return {
                    "subject_umbrella": umbrella,
                    "operational_trigger": matches[0],
                    "subject_family": matches[:3],
                }
        return {
            "subject_umbrella": "loss_of_control",
            "operational_trigger": "concrete workplace process",
            "subject_family": ["workplace process", "verification"],
        }

    def _with_topic_variety_metadata(self, idea: dict[str, Any]) -> dict[str, Any]:
        if idea.get("subject_umbrella") and idea.get("operational_trigger") and idea.get("subject_family"):
            return idea
        enriched = dict(idea)
        enriched.update(
            self._topic_variety_metadata(
                str(idea.get("title") or ""),
                str(idea.get("recommended_angle") or ""),
            )
        )
        return enriched

    def _add_topic_variety_metadata(self, ideas: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [self._with_topic_variety_metadata(idea) for idea in ideas]

    def _underused_subject_umbrellas(self, ideas: list[dict[str, Any]], limit: int = 4) -> list[str]:
        used = [str(idea.get("subject_umbrella") or "") for idea in ideas[:5]]
        counts = {umbrella: used.count(umbrella) for umbrella in SUBJECT_UMBRELLA_TRIGGER_MAP}
        return [umbrella for umbrella, _count in sorted(counts.items(), key=lambda item: (item[1], item[0]))][:limit]

    def _metric_topic_ideas(self, metric_signals: dict[str, Any]) -> list[dict[str, Any]]:
        templates = [
            (
                "concrete operational",
                "When the Version Label Is Stale",
                "turn a stale version label into a concrete verify-before-sending method",
            ),
            (
                "ordinary objects",
                "When the Dashboard Filter Is Wrong",
                "make the visible work object the trigger: verify filter, source, and date before reacting",
            ),
            (
                "resource constraints",
                "When the Budget Line Gets Cut",
                "show the three-column method: what still matters, what stops, and what can ship smaller",
            ),
            (
                "ambition",
                "When the Promotion Window Opens",
                "turn ambition into one controllable next action instead of attention theft",
            ),
            (
                "criticism",
                "When the Client Note Needs One Clarifying Question",
                "turn critical feedback into one clarifying question before defending or rewriting",
            ),
            (
                "feedback",
                "When the Client Note Needs One Clarifying Question",
                "turn critical feedback into one clarifying question before defending or rewriting",
            ),
            (
                "attention-control",
                "When the Calendar Block Gets Broken",
                "show how to protect one work block after an interruption without spiraling",
            ),
            (
                "attention control",
                "When the Calendar Block Gets Broken",
                "show how to protect one work block after an interruption without spiraling",
            ),
            (
                "mess",
                "When the Handoff Has No Owner",
                "turn a messy handoff into a concrete ownership-and-next-action scenario",
            ),
            (
                "cleaning",
                "When the Decision Record Is Incomplete",
                "show how to repair an incomplete decision trail without blame or panic",
            ),
            (
                "boundary",
                "When the Handoff Has No Owner",
                "show one small boundary: clarify owner, next step, and evidence before absorbing extra work",
            ),
            (
                "approval",
                "When the Review Comment Feels Personal",
                "turn approval pressure into a concrete review-comment scenario with one verification move",
            ),
            (
                "disagreement",
                "When the Review Comment Feels Personal",
                "show how disagreement triggers approval pressure, then give one Stoic move for separating fact from ego",
            ),
            (
                "deadline",
                "When the Export Timestamp Is Stale",
                "replace generic rushing with a concrete timestamp-check method before sending work",
            ),
            (
                "rushing",
                "When the Export Timestamp Is Stale",
                "replace generic rushing with a concrete timestamp-check method before sending work",
            ),
            (
                "urgency",
                "When the Dashboard Filter Is Wrong",
                "frame urgency as the moment to verify filter, source, and date before deciding",
            ),
            (
                "priority",
                "When the Handoff Has No Owner",
                "turn priority churn into a concrete owner/next-step clarification instead of another boss-pressure story",
            ),
            (
                "passive aggression",
                "When the Review Comment Feels Personal",
                "turn passive-aggressive wording into a fact-vs-story review comment scenario",
            ),
            (
                "conflict",
                "When the Review Comment Feels Personal",
                "turn workplace friction into a concrete written-review scenario instead of another coworker/boss confrontation",
            ),
            (
                "disrespect",
                "When the Review Comment Feels Personal",
                "turn disrespect framing into a concrete written-review scenario instead of another coworker/boss confrontation",
            ),
            (
                "status",
                "Stop Playing Status Games At Work",
                "show how status friction loses power when the viewer stops performing for approval",
            ),
            (
                "strategic patience",
                "Strategic Patience Is a Workplace Power Move",
                "frame patience as leverage, not passivity",
            ),
            (
                "patience",
                "Strategic Patience Is a Workplace Power Move",
                "frame patience as leverage, not passivity",
            ),
            (
                "discipline",
                "Build Discipline Without Burning Out",
                "make discipline a system of friction and boundaries, not self-punishment",
            ),
            (
                "focus",
                "When the Checklist Has One Missing Step",
                "show one concrete focus leak and one verification boundary before resuming work",
            ),
            (
                "overexplaining",
                "Stop Overexplaining At Work",
                "turn overexplaining into an approval-seeking trap the viewer can interrupt",
            ),
            (
                "anxiety",
                "Your Work Anxiety Needs a Scenario, Not a Slogan",
                "attach anxiety to one specific workplace trigger so it does not become generic",
            ),
        ]
        signals = [str(item.get("label", "")) for item in metric_signals.get("tiktok_weightings", []) if isinstance(item, dict)]
        signals.extend(str(value) for value in metric_signals.get("winning_themes", []))
        ideas: list[dict[str, Any]] = []
        seen_titles: set[str] = set()
        for signal in signals:
            lower = signal.lower()
            for keyword, title, angle in templates:
                if keyword in lower and title not in seen_titles:
                    ideas.append(
                        {
                            "objective": "discovery" if keyword not in {"anxiety"} else "conversion",
                            "title": title,
                            "recommended_angle": angle,
                            "why_now": f"Ledger metric signals currently favor: {signal}",
                            "experiment_tag": "tiktok_conflict_batch" if keyword in {"conflict", "disrespect", "status", "strategic patience", "patience"} else "discovery_batch",
                            "metric_signal": signal,
                        }
                    )
                    seen_titles.add(title)
                    break
        return self._add_topic_variety_metadata(ideas[:5])

    def generate_topic_plan(self, niche: str = "stoicism for modern workers") -> dict[str, Any]:
        strategy = self.load_global_strategy()
        metric_signals = strategy.get("metric_signals", {}) if isinstance(strategy.get("metric_signals"), dict) else {}
        metric_ideas = self._metric_topic_ideas(metric_signals)
        discovery = [
            {
                "objective": "discovery",
                "title": "When the Dashboard Filter Is Wrong",
                "recommended_angle": "turn a wrong dashboard filter into a verify-before-react method",
                "why_now": "keeps proven workplace-tension packaging while moving away from repeated conflict/rush subjects",
                "experiment_tag": "operational_variety_batch",
            },
            {
                "objective": "discovery",
                "title": "When the Export Timestamp Is Stale",
                "recommended_angle": "show how one timestamp check prevents a rushed bad decision",
                "why_now": "concrete operational triggers give the channel fresher repeatable methods",
                "experiment_tag": "operational_variety_batch",
            },
            {
                "objective": "discovery",
                "title": "When the Handoff Has No Owner",
                "recommended_angle": "clarify owner, next step, and evidence before absorbing the mess",
                "why_now": "keeps boundary appeal without repeating coworker-disrespect framing",
                "experiment_tag": "operational_variety_batch",
            },
            {
                "objective": "discovery",
                "title": "When the Decision Record Is Incomplete",
                "recommended_angle": "repair the audit trail calmly before arguing about memory",
                "why_now": "tests non-conflict operational friction with a clear Stoic method",
                "experiment_tag": "operational_variety_batch",
            },
        ]
        conversion = [
            {
                "objective": "conversion",
                "title": "When the Phone Wins the Morning",
                "recommended_angle": "turn attention theft into one visible phone-boundary move before the first work block",
                "why_now": "identity/emotion framing converts better when attached to a concrete attention object",
                "experiment_tag": "conversion_batch",
            },
            {
                "objective": "conversion",
                "title": "When the Promotion Window Opens",
                "recommended_angle": "turn ambition into one controllable next action instead of attention theft",
                "why_now": "desire and status can convert without becoming another conflict story",
                "experiment_tag": "conversion_batch",
            },
            {
                "objective": "conversion",
                "title": "When the Calendar Has No White Space",
                "recommended_angle": "make calm a practical boundary around energy and calendar load",
                "why_now": "fatigue and overcommitment give the channel a fresher emotional-positioning lane",
                "experiment_tag": "conversion_batch",
            },
        ]
        balanced = []
        if niche:
            balanced.append(
                {
                    "objective": "balanced",
                    "title": f"How Stoicism Helps When {niche.title()} Feels Heavy",
                    "recommended_angle": "connect a concrete work burden to a calmer inner posture",
                    "why_now": "tests whether mixed packaging can bridge reach and conversion",
                    "experiment_tag": "balanced_batch",
                }
            )

        if metric_ideas:
            by_title: dict[str, dict[str, Any]] = {}
            for idea in metric_ideas + discovery:
                by_title.setdefault(str(idea.get("title", "")), idea)
            discovery = [idea for title, idea in by_title.items() if title]

        discovery = self._add_topic_variety_metadata(discovery)
        conversion = self._add_topic_variety_metadata(conversion)
        balanced = self._add_topic_variety_metadata(balanced)
        ideas = discovery + conversion + balanced
        payload = {
            "generated_at": datetime.now(UTC).isoformat(),
            "niche": niche,
            "strategy_generated_at": strategy.get("generated_at"),
            "source_files": strategy.get("source_files", []),
            "metric_signals": metric_signals,
            "format_steering": strategy.get("format_steering", []),
            "subject_umbrella_policy": "Rotate subject_umbrella: no more than 2 of the last 5 videos from one umbrella; prefer at least 4 umbrellas per week.",
            "underused_subject_umbrellas": self._underused_subject_umbrellas(ideas),
            "batches": {
                "discovery": discovery,
                "conversion": conversion,
                "balanced": balanced,
            },
            "ideas": ideas,
        }
        save_json(payload, self.topic_plan_path)
        save_json(payload, self.topic_ideas_path)
        return payload

    def load_topic_plan(self, niche: str = "stoicism for modern workers") -> dict[str, Any]:
        strategy = self.load_global_strategy()
        if self.topic_plan_path.exists():
            payload = load_json(self.topic_plan_path)
            if (
                isinstance(payload, dict)
                and payload.get("niche") == niche
                and payload.get("strategy_generated_at") == strategy.get("generated_at")
                and payload.get("subject_umbrella_policy")
                and all(isinstance(idea, dict) and idea.get("subject_umbrella") for idea in payload.get("ideas", [])[:5])
            ):
                return payload
        return self.generate_topic_plan(niche=niche)

    def generate_topic_ideas(self, niche: str = "stoicism for modern workers") -> dict[str, Any]:
        return self.generate_topic_plan(niche=niche)

    def load_topic_ideas(self, niche: str = "stoicism for modern workers") -> dict[str, Any]:
        return self.load_topic_plan(niche=niche)
