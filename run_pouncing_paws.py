#!/usr/bin/env python3
"""Pouncing Paws - Daily AI News Fetcher

This script fetches AI news from the last 24 hours, scores stories 1-10,
filters high-scoring stories (7+), and saves them to output/jobs/
"""

import asyncio
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.stages.news_fetcher import NewsFetcher
from src.config import Channel, settings
from src.news_registry import news_registry


async def run_pouncing_paws():
    """Run the Pouncing Paws daily AI news fetch."""
    print("=" * 80)
    print("Pouncing Paws - Daily AI News Fetcher")
    print("=" * 80)
    
    # Generate job ID
    job_id = f"pouncing-paws-{datetime.now().strftime('%Y-%m-%dT%H-%M-%S')}"
    print(f"\nJob ID: {job_id}")
    
    # Coverage window
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=24)
    print(f"\nCoverage window: Last 24 hours ({cutoff.strftime('%Y-%m-%d %H:%M')} UTC to {now.strftime('%Y-%m-%d %H:%M')} UTC)")
    
    # Check covered_news.json for duplicates
    print("\nChecking covered_news.json to avoid duplicates...")
    covered_paths = Path.home() / ".hermes" / "content-pipeline" / "workspace" / "output" / "jobs" / "covered_news.json"
    if covered_paths.exists():
        with open(covered_paths, 'r') as f:
            covered_data = json.load(f)
        
        # Extract all URLs from covered_news.json
        covered_urls = set()
        if isinstance(covered_data, dict) and "coverage" in covered_data:
            for entry in covered_data.get("coverage", []):
                for story in entry.get("stories", []):
                    url = str(story.get("url", "") or story.get("headline", "") or "").strip().lower()
                    if url:
                        # Normalize URL
                        url = url.split('#', 1)[0].split('?', 1)[0].rstrip('/')
                        covered_urls.add(url)
        
        print(f"Previously covered URLs: {len(covered_urls)}")
    else:
        covered_urls = set()
        print("No covered_news.json found, starting fresh")
    
    # Fetch news stories
    print("\n" + "-" * 80)
    print("Fetching AI news from RSS feeds...")
    print("-" * 80)
    
    fetcher = NewsFetcher(channel=Channel.STOIC_MODERNIZED)
    stories = await fetcher.fetch_stories(
        topic="AI news",
        summarize=False,
        skip_urls=covered_urls,
        hours_back=24,
        min_quality=0.5
    )
    
    print(f"\nFound {len(stories)} unique high-quality stories")
    
    # Score and filter stories
    print("\n" + "-" * 80)
    print("Scoring stories (1-10) and filtering high-scoring ones (7+)...")
    print("-" * 80)
    
    scored_stories = []
    for story in stories:
        score = score_story(story)
        story.score = score
        scored_stories.append(story)
        
        status = "✅" if score >= 7 else "   "
        print(f"{status} [{score:2d}/10] {story.title[:80]}")
        print(f"   Source: {story.source} | URL: {story.url[:60]}...")
    
    # Filter high-scoring stories (7+)
    high_score_stories = [s for s in scored_stories if s.score >= 7]
    print(f"\nHigh-scoring stories (7+): {len(high_score_stories)}")
    
    # Take top 5
    top_stories = sorted(high_score_stories, key=lambda s: s.score, reverse=True)[:5]
    print(f"Selected top {len(top_stories)} stories for output")
    
    # Save to output/jobs/
    print("\n" + "-" * 80)
    print("Saving results...")
    print("-" * 80)
    
    job_dir = settings.output_dir / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    
    output_data = {
        "job_id": job_id,
        "timestamp": now.isoformat(),
        "coverage_period": f"{cutoff.strftime('%Y-%m-%d %H:%M')} to {now.strftime('%Y-%m-%d %H:%M')} (24 hours)",
        "total_stories_found": len(stories),
        "high_score_stories_count": len(high_score_stories),
        "top_stories_count": len(top_stories),
        "stories": []
    }
    
    for i, story in enumerate(top_stories, 1):
        story_data = {
            "rank": i,
            "score": story.score,
            "title": story.title,
            "url": story.url,
            "source": story.source,
            "summary": story.summary or story.snippet or "",
            "published": story.content[:200] if story.content else "",
        }
        output_data["stories"].append(story_data)
        print(f"\n{i}. [{story.score}/10] {story.title[:70]}")
        print(f"   Source: {story.source}")
        print(f"   Summary: {story.summary[:150]}...")
    
    # Save output file
    output_path = job_dir / "pouncing_paws_output.json"
    with open(output_path, 'w') as f:
        json.dump(output_data, f, indent=2)
    
    print(f"\n✅ Saved to: {output_path}")
    
    # Update covered_news.json
    print("\nUpdating covered_news.json...")
    new_entries = news_registry.build_entries_for_job(
        job_id=job_id,
        channel=Channel.STOIC_MODERNIZED,
        topic="Top 5 AI News",
        video_title="Top 5 AI News Today",
        sources=[{
            "title": s.title,
            "url": s.url,
            "note": s.summary or "",
            "source": s.source,
        } for s in top_stories]
    )
    added_count = news_registry.add_entries(Channel.STOIC_MODERNIZED, new_entries)
    print(f"✅ Added {added_count} new entries to covered_news.json")
    
    # Summary
    print("\n" + "=" * 80)
    print("Pouncing Paws Complete!")
    print("=" * 80)
    print(f"Job ID: {job_id}")
    print(f"Stories found: {len(stories)}")
    print(f"High-scoring (7+): {len(high_score_stories)}")
    print(f"Selected for output: {len(top_stories)}")
    print(f"Output directory: {job_dir}")
    print(f"\nReady for main pipeline at 8 AM")
    print("=" * 80)
    
    return output_data


def score_story(story) -> int:
    """Score a story 1-10 based on impact, novelty, source credibility, and urgency."""
    score = 5.0  # Base score
    
    # Source credibility (0-3 points)
    source_scores = {
        "official": 3.0,
        "blog": 2.5,
        "news": 2.0,
        "article": 1.5,
        "forum": 1.0,
        "web": 0.5,
    }
    score += source_scores.get(story.source.lower(), 1.0)
    
    # Title length and specificity (0-1 point)
    title = story.title or ""
    if len(title) > 50:
        score += 0.5
    if any(word in title.lower() for word in ["launch", "release", "announces", "unveils"]):
        score += 0.5
    
    # Content depth (0-1 point)
    content = story.content or story.summary or ""
    if len(content) > 500:
        score += 1.0
    elif len(content) > 200:
        score += 0.5
    
    # Novelty indicators (0-1 point)
    novelty_words = ["breakthrough", "first", "new", "launch", "unveils", "introduces", "releases"]
    if any(word in (story.title + story.summary).lower() for word in novelty_words):
        score += 0.5
    
    # Major company involvement (0-0.5 points)
    major_companies = ["openai", "anthropic", "google", "deepmind", "nvidia", "meta", "microsoft"]
    if any(company in (story.title + story.summary).lower() for company in major_companies):
        score += 0.5
    
    return min(10, max(1, int(score)))


if __name__ == "__main__":
    asyncio.run(run_pouncing_paws())
