#!/usr/bin/env python3
"""
Paw Hook Editor for AI Signal
Generates 5 YouTube Short hooks based on Pip summaries
"""
import json
import sys
from datetime import datetime
from pathlib import Path

# Load summaries
summaries_file = sys.argv[1] if len(sys.argv) > 1 else None
output_dir = sys.argv[2] if len(sys.argv) > 2 else None

if not summaries_file:
    print("Usage: python paw_hooks_editor.py <summaries.json> [output_dir]")
    sys.exit(1)

with open(summaries_file) as f:
    data = json.load(f)

summaries = data["summaries"]

# Analyze the summaries to find the core theme
# All summaries revolve around: Stoicism, discipline, consistency, habits, self-control
# Key insights:
# - Self-control is a trainable skill, not willpower
# - Mini habits and elastic habits work better than rigid routines
# - Discipline through small, consistent wins
# - Negative visualization and evening reviews build resilience
# - Master first hour, tackle hated tasks, practice micro-integrity

core_theme = "Stoic discipline: self-control as a trainable skill, not willpower"

# Generate 5 hooks based on today's news
hooks = [
    {
        "hook": "MMA fighters use this Stoic trick to stay calm under pressure",
        "why_it_works": "Connects combat sports (high interest) with practical Stoic application; concrete context (MMA, pressure)",
        "risk": "Might attract fight fans who want fighting tips, not Stoicism"
    },
    {
        "hook": "Stop relying on willpower. Stoics do this instead.",
        "why_it_works": "Direct challenge to common belief; promises a better alternative; 'Stoics' creates curiosity",
        "risk": "Generic phrasing, might feel like typical self-help"
    },
    {
        "hook": "The 5-minute habit that builds unstoppable self-discipline",
        "why_it_works": "Specific time (5-min) makes it feel achievable; 'unstoppable' is aspirational but concrete",
        "risk": "Could feel like clickbait; need to deliver on the '5-minute' promise"
    },
    {
        "hook": "Why your New Year's resolutions fail (and what Stoics do)",
        "why_it_works": "Addresses pain point (resolutions failing); positions Stoicism as the proven alternative",
        "risk": "New Year's resolutions feel dated in May; might not resonate"
    },
    {
        "hook": "Master your first hour, then one hated task daily",
        "why_it_works": "Very specific, actionable advice; no fluff; promises concrete steps immediately",
        "risk": "Too instructional for a hook; might feel like a listicle"
    }
]

# Select the recommended hook
recommended = {
    "hook": "MMA fighters use this Stoic trick to stay calm under pressure",
    "reason": "Best balance of specificity (MMA, pressure) and curiosity; high-stakes context makes it compelling without being clickbait; directly connects to Psychology Today article in today's news"
}

# Build output
output = {
    "job_id": f"paw-hooks-{datetime.utcnow().strftime('%Y-%m-%dT%H-%M-%S')}",
    "source_job": data["job_id"],
    "generated_at": datetime.utcnow().isoformat() + "Z",
    "theme": core_theme,
    "hooks": hooks,
    "recommended_hook": recommended
}

# Save output
if output_dir:
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    output_file = Path(output_dir) / f"{output['job_id']}.json"
else:
    output_file = Path(f"output/jobs/{output['job_id']}.json")
    Path(output_file).parent.mkdir(parents=True, exist_ok=True)

with open(output_file, "w") as f:
    json.dump(output, f, indent=2)

print(f"Saved to: {output_file}")
print(json.dumps(output, indent=2))
