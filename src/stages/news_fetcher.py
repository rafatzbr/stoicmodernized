"""Standalone news fetcher for the AI Signal news selection dashboard.

Fetches AI news stories via RSS feeds (official blogs, community sources),
reads article text, and LLM-summarizes each story. Returns structured story
data for the frontend to display.
"""

from __future__ import annotations

import asyncio
import json
import re
from datetime import datetime, timedelta
from html import unescape
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse, parse_qs, urlencode

import httpx
from bs4 import BeautifulSoup
from dateutil import parser as date_parser

from src.config import Channel, settings
from src.models import ResearchSource
from src.news_registry import news_registry
from src.utils import save_json

# Official AI company RSS feeds - primary sources for news
OFFICIAL_RSS_FEEDS = {
    "openai": "https://openai.com/blog/index.xml",
    "anthropic": "https://www.anthropic.com/index.xml",
    "google_ai": "https://ai.google/blog/rss.xml",
    "nvidia": "https://blogs.nvidia.com/blog/rss/",
    "huggingface": "https://huggingface.co/blog/rss.xml",
    "meta_ai": "https://ai.meta.com/blog/rss/",
    "deepmind": "https://deepmind.google/discover/blog/",
}

# Community and news RSS feeds - secondary sources
COMMUNITY_RSS_FEEDS = {
    "reddit_ml": "https://www.reddit.com/r/MachineLearning/top/.rss?limit=25",
    "reddit_llama": "https://www.reddit.com/r/LocalLLaMA/top/.rss?limit=25",
    "techcrunch_ai": "https://techcrunch.com/category/artificial-intelligence/feed/",
    "arstechnica_ai": "https://arstechnica.com/feed/category/ai",
    "wired_ai": "https://www.wired.com/feed/category/artificial-intelligence/rss",
}

# Source priority ordering (higher = more trusted)
SOURCE_PRIORITY = {
    "official": 100,
    "blog": 80,
    "news": 70,
    "article": 60,
    "forum": 50,
    "web": 30,
}


class StorySummary:
    """A single fetched and summarized news story."""

    def __init__(
        self,
        title: str,
        url: str,
        source: str,
        relevance: float,
        summary: Optional[str] = None,
        snippet: Optional[str] = None,
        content: Optional[str] = None,
        original_title: Optional[str] = None,
    ):
        self.title = title
        self.url = url
        self.source = source
        self.relevance = relevance
        self.summary = summary
        self.snippet = snippet
        self.content = content
        self.original_title = original_title

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "url": self.url,
            "source": self.source,
            "relevance": self.relevance,
            "summary": self.summary,
            "snippet": self.snippet,
            "content": self.content,
            "original_title": self.original_title,
        }


class NewsFetcher:
    """Fetches and summarizes AI news stories from RSS feeds."""

    def __init__(self, channel: Channel = Channel.STOIC_MODERNIZED):
        self.channel = channel
        self.llama_base_url = settings.local_llm_base_url
        self._article_reads: list[dict[str, Any]] = []
        self._rss_cache: dict[str, list[dict]] = {}  # Cache for RSS feeds
        self._cache_ttl = 300  # 5 minutes cache TTL

    @property
    def article_reads(self) -> list[dict[str, Any]]:
        return self._article_reads

    async def fetch_stories(self, topic: str = "AI news", summarize: bool = False, skip_urls: set[str] | None = None, hours_back: int = 48, min_quality: float = 0.5) -> list[StorySummary]:
        """Fetch stories from RSS feeds with quality filtering.

        Args:
            topic: Topic filter (currently ignored, returns all AI news)
            summarize: Whether to generate LLM summaries (slow)
            skip_urls: URLs to exclude (deduplication)
            hours_back: Only fetch stories from last N hours (default 48)
            min_quality: Minimum overall quality score (default 0.5)
        """
        sources = await self._fetch_from_rss_feed(hours_back=hours_back)
        
        # Read articles
        articles = await self._read_articles(sources)
        
        # Filter by quality
        quality_filtered = []
        for article in articles:
            quality = self.validate_story_quality(article)
            if quality["passes_threshold"] and quality["overall_score"] >= min_quality:
                quality_filtered.append(article)
            else:
                print(f"[NewsFetcher] Filtered low-quality story: {article.title[:80]} (score: {quality['overall_score']})")
        
        if len(quality_filtered) < 5:
            print(f"[NewsFetcher] Warning: Only {len(quality_filtered)} high-quality stories found, relaxing quality filter")
            # Re-fetch with lower threshold
            articles = await self._read_articles(sources)
            quality_filtered = [a for a in articles if self.validate_story_quality(a)["overall_score"] >= 0.3]
        
        if summarize:
            return await self._read_and_summarize(quality_filtered)
        return quality_filtered

    async def _fetch_from_rss_feed(self, hours_back: int = 48) -> list[ResearchSource]:
        """Fetch stories from RSS feeds with freshness filtering. Falls back to SearXNG if RSS fails."""
        from datetime import datetime, timezone
        
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=hours_back)
        all_stories: list[dict[str, Any]] = []
        fetch_errors = []
        
        print(f"[NewsFetcher] Attempting RSS feed fetch (last {hours_back}h)...")
        
        # Fetch from official feeds first
        async with httpx.AsyncClient(follow_redirects=True, timeout=15.0, verify=False) as client:
            for source_name, feed_url in OFFICIAL_RSS_FEEDS.items():
                try:
                    stories = await self._fetch_rss_feed(client, feed_url, source_name, cutoff_time)
                    all_stories.extend(stories)
                    print(f"[NewsFetcher] {source_name}: {len(stories)} stories")
                except Exception as e:
                    fetch_errors.append(f"{source_name}: {e}")
            
            # Fetch from community feeds
            for source_name, feed_url in COMMUNITY_RSS_FEEDS.items():
                try:
                    stories = await self._fetch_rss_feed(client, feed_url, source_name, cutoff_time)
                    all_stories.extend(stories)
                    print(f"[NewsFetcher] {source_name}: {len(stories)} stories")
                except Exception as e:
                    fetch_errors.append(f"{source_name}: {e}")
        
        if not all_stories:
            print(f"[NewsFetcher] RSS feeds failed, falling back to SearXNG search")
            return await self._search_searxng("AI news today OpenAI Anthropic Google 2026", skip_urls=set())
        
        if fetch_errors:
            print(f"[NewsFetcher] Fetch errors: {fetch_errors[:3]}")
        
        # Deduplicate and sort by recency
        seen_urls = set()
        unique_stories = []
        for story in sorted(all_stories, key=lambda x: x.get('published', datetime.min.replace(tzinfo=timezone.utc)), reverse=True):
            url = story['url'].strip().lower().split('#', 1)[0].split('?', 1)[0].rstrip('/')
            if url not in seen_urls:
                # Skip if already covered
                seen_urls.add(url)
                unique_stories.append(story)
        
        # Convert to ResearchSource format
        sources: list[ResearchSource] = []
        for i, story in enumerate(unique_stories[:10]):  # Take top 10
            relevance = max(0.85, 0.95 - (i * 0.03))  # Higher base relevance for RSS
            sources.append(
                ResearchSource(
                    title=story['title'],
                    url=story['url'],
                    note=story.get('summary', story.get('description', ''))[:500],
                    relevance=round(relevance, 2),
                    source=story['source'],
                )
            )
        
        print(f"[NewsFetcher] Total unique stories: {len(sources)}")
        return sources
    
    async def _search_searxng(self, topic: str, skip_urls: set[str] | None = None) -> list[ResearchSource]:
        """Search SearXNG for stories with improved query and filtering."""
        query = self._build_query(topic)
        searxng_base_url = "https://search.zweb"
        max_retries = 3
        base_delay = 2
        data: dict[str, Any] = {}

        for attempt in range(max_retries):
            try:
                async with httpx.AsyncClient(timeout=30.0, verify=False) as client:
                    response = await client.get(
                        f"{searxng_base_url}/search",
                        params={"q": query, "format": "json", "engines": "google,bing,duckduckgo", "categories": "news"},
                        headers={"User-Agent": "Mozilla/5.0 (AI Signal News Bot)", "Accept": "application/json"},
                    )
                    response.raise_for_status()
                    data = response.json()
                    break
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429 and attempt < max_retries - 1:
                    delay = base_delay * (2 ** attempt)
                    print(f"[SearXNG] Rate limited. Retrying in {delay}s... (attempt {attempt + 1}/{max_retries})")
                    await asyncio.sleep(delay)
                    continue
                raise
            except Exception as e:
                if attempt < max_retries - 1:
                    delay = base_delay * (2 ** attempt)
                    print(f"[SearXNG] Search error: {e}. Retrying in {delay}s... (attempt {attempt + 1}/{max_retries})")
                    await asyncio.sleep(delay)
                    continue
                raise

        sources: list[ResearchSource] = []
        skip_urls = skip_urls or set()
        limit = 15
        duplicate_skips = 0
        
        results = data.get("results", [])
        print(f"[SearXNG] Found {len(results)} results")
        
        for item in results:
            title = (item.get("title") or "").strip()
            url = (item.get("url") or "").strip()
            snippet = (item.get("content") or item.get("snippet") or "").strip()
            
            if not title or not url:
                continue
            
            # Filter out low-quality results
            if len(snippet) < 50 and len(title) < 20:
                continue
            
            # Skip obvious junk
            if any(junk in title.lower() for junk in ["slot", "gambling", "casino", "crypto", "pump", "moon"]):
                continue
            
            normalized_url = url.strip().lower().split("#", 1)[0].split("?", 1)[0].rstrip("/")
            if normalized_url in skip_urls:
                continue
            
            # Higher base relevance for search results
            index = len(sources)
            relevance = max(0.70, 0.92 - (index * 0.04))
            sources.append(
                ResearchSource(
                    title=title,
                    url=url,
                    note=snippet,
                    relevance=round(relevance, 2),
                    source=self._infer_source(url),
                )
            )
            if len(sources) >= limit:
                break
        
        if duplicate_skips:
            print(f"[SearXNG] Skipped {duplicate_skips} previously covered story candidates")
        print(f"[SearXNG] Returning {len(sources)} sources")
        return sources
    
    async def _fetch_rss_feed(self, client: httpx.AsyncClient, feed_url: str, source_name: str, cutoff_time: datetime) -> list[dict[str, Any]]:
        """Fetch and parse a single RSS feed with redirect handling."""
        # Enable redirects
        client_with_redirects = httpx.AsyncClient(follow_redirects=True, timeout=15.0, verify=False)
        try:
            response = await client_with_redirects.get(feed_url, headers={"User-Agent": "Mozilla/5.0 (AI Signal News Bot)"})
            response.raise_for_status()
        except httpx.HTTPError as e:
            raise e
        finally:
            await client_with_redirects.aclose()
        
        # Parse XML
        import xml.etree.ElementTree as ET
        try:
            root = ET.fromstring(response.text)
        except Exception as e:
            print(f"[NewsFetcher] Failed to parse XML for {feed_url}: {e}")
            return []
        
        stories = []
        ns = {'atom': 'http://www.w3.org/2005/Atom', 'rss': 'http://www.rssboard.org/rss-specification'}
        
        # Handle different RSS formats
        items = root.findall('.//item') or root.findall('.//{http://www.w3.org/2005/Atom}entry')
        
        for item in items:
            try:
                # Extract title
                title_elem = item.find('title') or item.find('.//{http://www.w3.org/2005/Atom}title')
                title = title_elem.text.strip() if title_elem is not None and title_elem.text else ''
                
                # Extract link
                link_elem = item.find('link') or item.find('.//{http://www.w3.org/2005/Atom}link')
                if link_elem is not None:
                    url = link_elem.get('href') or link_elem.text or ''
                else:
                    continue
                
                # Extract description/summary
                desc_elem = item.find('description') or item.find('summary') or item.find('.//{http://www.w3.org/2005/Atom}summary')
                summary = desc_elem.text.strip() if desc_elem is not None and desc_elem.text else ''
                
                # Extract published date
                pub_elem = item.find('pubDate') or item.find('dc:date') or item.find('.//{http://purl.org/dc/elements/1.1/}date') or item.find('.//{http://www.w3.org/2005/Atom}published')
                if pub_elem is not None and pub_elem.text:
                    try:
                        published = date_parser.parse(pub_elem.text)
                        if published.tzinfo is None:
                            published = published.replace(tzinfo=timezone.utc)
                    except Exception:
                        published = datetime.min.replace(tzinfo=timezone.utc)
                else:
                    published = datetime.min.replace(tzinfo=timezone.utc)
                
                # Filter by recency
                if published < cutoff_time:
                    continue
                
                # Clean up summary (remove HTML tags)
                summary = re.sub(r'<[^>]+>', '', summary)
                summary = ' '.join(summary.split())[:800]
                
                stories.append({
                    'title': title,
                    'url': url,
                    'summary': summary,
                    'source': source_name,
                    'published': published,
                })
            except Exception as e:
                continue  # Skip malformed items
        
        return stories

    async def _read_articles(self, sources: list[ResearchSource]) -> list[StorySummary]:
        """Fetch readable article content without expensive LLM summaries."""
        self._article_reads = []
        tasks = [self._fetch_article(source.url) for source in sources]
        articles = await asyncio.gather(*tasks, return_exceptions=True)
        results: list[StorySummary] = []

        for source, article in zip(sources, articles):
            title = source.title
            content = ""
            if isinstance(article, dict):
                content = str(article.get("content") or "")
                article_title = str(article.get("title") or "").strip()
                if article_title and ("..." in title or len(article_title) > len(title)):
                    title = article_title

            note = content[:600].strip() or source.note
            results.append(
                StorySummary(
                    title=title,
                    url=source.url,
                    source=source.source,
                    relevance=source.relevance,
                    summary=note,
                    snippet=source.note,
                    content=content or source.note,
                    original_title=source.title,
                )
            )
            self._article_reads.append(
                {
                    "title": title,
                    "url": source.url,
                    "source": source.source,
                    "read_success": bool(content),
                    "article_summary": None,
                    "content_chars": len(content),
                }
            )
        return results

    async def _read_and_summarize(self, sources: list[ResearchSource]) -> list[StorySummary]:
        """Fetch article text and LLM-summarize each source."""
        articles = await self._read_articles(sources)
        for story in articles:
            if story.content:
                source = ResearchSource(
                    title=story.title,
                    url=story.url,
                    note=story.snippet or "",
                    relevance=story.relevance,
                    source=story.source,
                )
                summary = await self._summarize_article(source, story.content)
                if summary:
                    story.summary = summary
        return articles

    async def _fetch_article(self, url: str) -> dict[str, str]:
        try:
            async with httpx.AsyncClient(timeout=12.0, follow_redirects=True, verify=False) as client:
                response = await client.get(
                    url,
                    headers={
                        "User-Agent": "Mozilla/5.0",
                        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    },
                )
                response.raise_for_status()
        except Exception:
            return {"title": "", "content": ""}

        content_type = response.headers.get("content-type", "")
        if "text/html" not in content_type and "application/xhtml+xml" not in content_type:
            return {"title": "", "content": ""}

        return {
            "title": self._extract_title(response.text),
            "content": self._extract_readable_text(response.text),
        }

    async def _fetch_article_text(self, url: str) -> str:
        try:
            async with httpx.AsyncClient(timeout=20.0, follow_redirects=True, verify=False) as client:
                response = await client.get(
                    url,
                    headers={
                        "User-Agent": "Mozilla/5.0",
                        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    },
                )
                response.raise_for_status()
        except Exception:
            return ""

        content_type = response.headers.get("content-type", "")
        if "text/html" not in content_type and "application/xhtml+xml" not in content_type:
            return ""

        return self._extract_readable_text(response.text)

    def _extract_title(self, html: str) -> str:
        soup = BeautifulSoup(html, "html.parser")
        for selector in (
            ('meta', {'property': 'og:title'}),
            ('meta', {'name': 'twitter:title'}),
        ):
            tag = soup.find(*selector)
            content = tag.get("content") if tag else None
            if content:
                return self._clean_title(content)
        if soup.title and soup.title.string:
            return self._clean_title(soup.title.string)
        return ""

    def _clean_title(self, title: str) -> str:
        title = unescape(re.sub(r"\s+", " ", title).strip())
        return title.strip()

    def _extract_readable_text(self, html: str) -> str:
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "noscript", "svg", "form", "button", "iframe", "aside", "nav", "header", "footer"]):
            tag.decompose()

        candidates = []
        candidates.extend(soup.find_all("article"))
        main = soup.find("main")
        if main:
            candidates.append(main)
        candidates.extend(soup.select('[role="main"], [class*="article"], [class*="story"], [class*="content"], [class*="post"]'))
        if not candidates and soup.body:
            candidates.append(soup.body)

        best = max(candidates, key=self._candidate_score, default=soup)
        paragraphs = self._extract_paragraphs_from_node(best)
        if len(" ".join(paragraphs)) < 500 and soup.body:
            paragraphs = self._extract_paragraphs_from_node(soup.body)
        return "\n\n".join(paragraphs)[:30000]

    def _candidate_score(self, node) -> int:
        parts = []
        for tag in node.find_all(["p", "blockquote"], recursive=True):
            text = tag.get_text(" ", strip=True)
            text = unescape(re.sub(r"\s+", " ", text).strip())
            if self._is_article_paragraph(text):
                parts.append(text)
        long_parts = [part for part in parts if len(part) >= 80]
        return sum(len(part) for part in long_parts) + (len(long_parts) * 250)

    def _extract_paragraphs_from_node(self, node) -> list[str]:
        parts: list[str] = []
        paragraph_tags = node.find_all(["h1", "h2", "h3", "p", "blockquote"], recursive=True)
        list_tags = node.find_all("li", recursive=True)
        tags = paragraph_tags if len(paragraph_tags) >= 3 else [*paragraph_tags, *list_tags]
        for tag in tags:
            text = tag.get_text(" ", strip=True)
            text = unescape(re.sub(r"\s+", " ", text).strip())
            if not self._is_article_paragraph(text):
                continue
            if tag.name == "li" and not text.startswith("• "):
                text = f"• {text}"
            normalized = text.removeprefix("• ").strip().lower()
            previous_normalized = parts[-1].removeprefix("• ").strip().lower() if parts else ""
            if normalized != previous_normalized:
                parts.append(text)
        return parts

    def _is_article_paragraph(self, text: str) -> bool:
        if len(text) < 45:
            return False
        lowered = text.lower()
        junk_phrases = (
            "sign in", "subscribe", "advertisement", "cookies", "privacy policy",
            "terms of use", "follow us", "share this", "read more", "related articles",
            "download app", "enable javascript", "all rights reserved", "newsletter",
            "dedicated team of journalists", "news coverage spans", "missing:",
        )
        if any(phrase in lowered for phrase in junk_phrases):
            return False
        alpha_count = sum(ch.isalpha() for ch in text)
        # Lower threshold to be more permissive
        return alpha_count >= 20
    
    def validate_story_quality(self, story: StorySummary) -> dict[str, Any]:
        """Validate quality of a news story.
        
        Returns dict with quality metrics:
        - title_quality: 0-1 (length, clarity)
        - content_quality: 0-1 (extraction success, word count)
        - source_quality: 0-1 (source type trustworthiness)
        - overall_score: weighted average
        """
        # Title quality
        title = story.title or ""
        title_quality = min(1.0, len(title) / 100) if len(title) > 10 else 0.3
        
        # Content quality
        content = story.content or story.summary or ""
        content_quality = 0.0
        if len(content) > 500:
            content_quality = 0.9
        elif len(content) > 200:
            content_quality = 0.6
        elif len(content) > 50:
            content_quality = 0.3
        
        # Source quality (higher = more trusted)
        source_score = SOURCE_PRIORITY.get(story.source, 50)
        source_quality = source_score / 100.0
        
        # Overall score (weighted)
        overall = (title_quality * 0.2) + (content_quality * 0.5) + (source_quality * 0.3)
        
        return {
            "title_quality": round(title_quality, 2),
            "content_quality": round(content_quality, 2),
            "source_quality": round(source_quality, 2),
            "overall_score": round(overall, 2),
            "passes_threshold": overall >= 0.5,
        }

    async def _summarize_article(self, source: ResearchSource, article_text: str) -> Optional[str]:
        prompt = self._build_article_summary_prompt(source, article_text)
        try:
            async with httpx.AsyncClient(timeout=45.0) as client:
                response = await client.post(
                    self.llama_base_url,
                    json={
                        "model": settings.local_llm_model,
                        "messages": [
                            {"role": "system", "content": "You summarize source articles for a research pipeline. Output JSON only."},
                            {"role": "user", "content": prompt},
                        ],
                        "temperature": 0.2,
                        "max_tokens": 220,
                        "response_format": {"type": "json_object"},
                        "chat_template_kwargs": {"enable_thinking": False},
                    },
                )
                response.raise_for_status()
                data = response.json()
                content = data["choices"][0]["message"]["content"]
                payload = json.loads(content)
                summary = str(payload.get("summary") or "").strip()
                return summary or None
        except Exception:
            return None

    def _build_article_summary_prompt(self, source: ResearchSource, article_text: str) -> str:
        return f"""
You are reading a news article for {settings.get_channel_name(self.channel)}.
Source title: {source.title}
URL: {source.url}

Read the article text and return JSON only:
{{"summary": "string"}}

Rules:
- summarize what the article actually says in 2-3 concise sentences
- mention the concrete development, who is involved, and why it matters
- stay factual and avoid hype
- do not invent details that are not in the text
- output JSON only

Article text:
{article_text}
""".strip()

    def _build_query(self, topic: str) -> str:
        return f"latest technology news {topic} OpenAI Anthropic Google Microsoft Nvidia"

    def _infer_source(self, url: str) -> str:
        lowered = url.lower()
        hostname = (urlparse(url).hostname or "").lower()
        official_hosts = {
            "openai.com", "www.openai.com",
            "anthropic.com", "www.anthropic.com",
            "blog.google", "googleblog.com", "blog.google.com",
            "blogs.microsoft.com", "microsoft.com", "www.microsoft.com",
            "blogs.nvidia.com", "nvidia.com", "www.nvidia.com",
        }
        if hostname in official_hosts:
            return "official"
        if hostname.endswith("wikipedia.org"):
            return "wikipedia"
        if hostname.endswith("reddit.com"):
            return "forum"
        if hostname.endswith("medium.com"):
            return "article"
        if "blog" in hostname or "dailystoic" in hostname or "modernstoicism" in hostname:
            return "blog"
        if "news" in hostname or "timesofindia" in hostname or "nytimes.com" in hostname or "theverge.com" in hostname:
            return "news"
        return "web"

    def save_article_reads(self, job_id: str) -> Optional[Path]:
        """Persist article read metadata for a job."""
        if not self._article_reads:
            return None
        job_dir = settings.jobs_dir / job_id
        job_dir.mkdir(parents=True, exist_ok=True)
        reads_path = job_dir / "article_reads.json"
        save_json(self._article_reads, reads_path)
        return reads_path
