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
            "stoic-modernized-tiktok-analytics-*.md",
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

    def generate_global_strategy(self) -> dict[str, Any]:
        source_files: list[str] = []
        snippets: list[str] = []
        for path in self._artifact_candidates():
            source_files.append(str(path))
            try:
                snippets.extend(self._extract_useful_lines(path.read_text(encoding="utf-8"), max_lines=20))
            except OSError:
                continue

        strategy = {
            "generated_at": datetime.now(UTC).isoformat(),
            "source_files": source_files,
            "evidence_excerpt": snippets[:50],
            "distribution": {
                "primary_surface": "shorts_feed",
                "device_priority": "mobile_first",
                "audience_profile": "mostly_unsubscribed",
                "secondary_surface": "linkedin_experiment",
                "tiktok_surface": "scenario_first_short_hooks",
            },
            "content_lanes": {
                "discovery": {
                    "share": 5,
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
                    "share": 2,
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
                    "share": 3,
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
                "prioritize_scenarios": [
                    "coworker disrespect",
                    "status games",
                    "strategic patience",
                    "discipline systems",
                    "overexplaining",
                    "meetings",
                    "focus friction",
                    "burnout tied to control",
                    "reactive messages",
                    "office politics",
                    "deadlines",
                    "overthinking",
                    "layoffs",
                ],
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
            "cta_style": "light comment prompt + optional follow CTA" if objective != "discovery" else "light comment prompt",
            "distribution_notes": [
                "mobile-first captions and framing",
                "shorts-feed hook matters more than SEO",
                "consider LinkedIn repost if topic is strongly workplace-relevant",
                "for TikTok, prefer scenario-first hooks and do not inherit YouTube resource-heavy captions",
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

    def generate_topic_plan(self, niche: str = "stoicism for modern workers") -> dict[str, Any]:
        strategy = self.load_global_strategy()
        discovery = [
            {
                "objective": "discovery",
                "title": "Your Coworker's Disrespect Only Wins If You React",
                "recommended_angle": "turn workplace disrespect into a composure-vs-reactivity scenario",
                "why_now": "TikTok data shows conflict/disrespect framing is currently the strongest reach lane",
                "experiment_tag": "tiktok_conflict_batch",
            },
            {
                "objective": "discovery",
                "title": "Strategic Patience Is a Workplace Power Move",
                "recommended_angle": "frame patience as leverage, not passivity",
                "why_now": "patience/power-move packaging is one of the strongest TikTok patterns",
                "experiment_tag": "tiktok_conflict_batch",
            },
            {
                "objective": "discovery",
                "title": "Stop Checking Slack Before Thinking",
                "recommended_angle": "show how notifications hijack focus before real work begins",
                "why_now": "mobile-first shorts feed rewards immediate workplace pain recognition",
                "experiment_tag": "discovery_batch",
            },
            {
                "objective": "discovery",
                "title": "What Marcus Aurelius Would Do Before Your 9 AM Meeting",
                "recommended_angle": "use a specific work ritual instead of generic philosophy",
                "why_now": "meeting-specific packaging matches proven concrete-work framing",
                "experiment_tag": "discovery_batch",
            },
        ]
        conversion = [
            {
                "objective": "conversion",
                "title": "Why Your Anxiety Wants a Script",
                "recommended_angle": "frame anxiety as a learned pattern the viewer can catch and interrupt",
                "why_now": "identity/emotion framing has shown the strongest subscriber conversion on YouTube, but needs sharper scenarios on TikTok",
                "experiment_tag": "conversion_batch",
            },
            {
                "objective": "conversion",
                "title": "You Do Not Need Everyone at Work to Like You",
                "recommended_angle": "approval-seeking at work becomes the central emotional trap",
                "why_now": "unsubscribed viewers may convert when the struggle feels personally seen",
                "experiment_tag": "conversion_batch",
            },
            {
                "objective": "conversion",
                "title": "Calm Is a Skill, Not a Personality",
                "recommended_angle": "reframe calm as trained self-command under pressure",
                "why_now": "gives the channel a repeatable emotional-positioning lane",
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

        payload = {
            "generated_at": datetime.now(UTC).isoformat(),
            "niche": niche,
            "strategy_generated_at": strategy.get("generated_at"),
            "source_files": strategy.get("source_files", []),
            "batches": {
                "discovery": discovery,
                "conversion": conversion,
                "balanced": balanced,
            },
            "ideas": discovery + conversion + balanced,
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
            ):
                return payload
        return self.generate_topic_plan(niche=niche)

    def generate_topic_ideas(self, niche: str = "stoicism for modern workers") -> dict[str, Any]:
        return self.generate_topic_plan(niche=niche)

    def load_topic_ideas(self, niche: str = "stoicism for modern workers") -> dict[str, Any]:
        return self.load_topic_plan(niche=niche)
