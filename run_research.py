#!/usr/bin/env python3
"""Run research stage for a specific job."""

import asyncio
import json
import sys
from pathlib import Path

# Add the project to the path
sys.path.insert(0, str(Path(__file__).parent))

from src.config import Channel, VideoMode, settings
from src.database import db
from src.stages.research import ResearchStage


async def main(topic: str, job_id: str, channel: Channel = Channel.STOIC_MODERNIZED):
    """Run research stage."""
    
    print(f"Running research for: {topic}")
    print(f"Job ID: {job_id}")
    
    # Ensure job directory exists
    job_dir = settings.jobs_dir / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    
    # Create job in database
    job_record = db.create_job(topic)
    actual_job_id = job_record.job_id
    print(f"Job ID: {actual_job_id}")
    
    # Run research
    research_stage = ResearchStage(job_id=actual_job_id, mock=False, channel=channel)
    results = await research_stage.run(topic=topic)
    
    # Save results
    research_path = job_dir / "research" / f"{actual_job_id}-research.json"
    research_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(research_path, 'w') as f:
        json.dump(results.model_dump(), f, indent=2)
    
    print(f"\n✓ Research complete!")
    print(f"Sources found: {len(results.sources)}")
    print(f"Saved to: {research_path}")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python run_research.py <topic> <job_id>")
        sys.exit(1)
    
    topic = sys.argv[1]
    job_id = sys.argv[2]
    channel = Channel.STOIC_MODERNIZED if len(sys.argv) < 4 else Channel(sys.argv[3])
    
    asyncio.run(main(topic, job_id, channel))
