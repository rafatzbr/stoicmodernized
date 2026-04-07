#!/usr/bin/env python3
"""
Stoic Modernized Image Prompt Generator

Generates valid image prompts using a base template + llama.cpp refinement.

Usage:
    python -m src.prompt_generator "subject here"

Examples:
    python -m src.prompt_generator "staying calm when work feels urgent"
    python -m src.prompt_generator "setting boundaries at work"
"""

import argparse
import json
import random
import sys
from pathlib import Path

import httpx

# Predefined elements for random combination
PROFESSIONS = [
    "office professional",
    "knowledge worker",
    "creative professional",
    "software engineer",
    "project manager",
    "team lead",
    "consultant",
]

ACTIONS = [
    "seated at a tidy desk writing",
    "pausing with hands resting on keyboard",
    "reviewing handwritten notes",
    "organizing workspace",
    "focusing on a physical notebook",
    "taking a mindful break",
    "reflecting while looking at a journal",
]

LOCATIONS = [
    "in a modern workplace",
    "at their home office desk",
    "in a quiet co-working space",
    "at a minimalist desk setup",
    "in a calm office environment",
]

CONCRETE_OBJECTS = [
    "notebook, pen, keyboard, and coffee mug visible",
    "phone placed face-down beside laptop",
    "physical journal with handwritten notes",
    "small succulent plant on desk corner",
    "water bottle and minimal items",
    "stress ball in hand",
    "cup of tea with steam rising",
]

BACKGROUNDS = [
    "blurred office activity",
    "soft focus window view",
    "subtle blurred figures in distance",
    "minimal office background",
    "calm neutral office wall",
]

FOREGROUNDS = [
    "organized workspace with controlled details",
    "clear focus on subject and notebook",
    "calm centered expression",
    "relaxed shoulders and posture",
    "mindful attention to task",
]

# Base style requirements (always included)
STYLE_KEYWORDS = "candid editorial photography, medium shot, slightly off-center, shallow depth of field, realistic skin texture, 35mm or 50mm lens, vertical 9:16"
LIGHTING = "soft natural window light"


def expand_subject(subject: str) -> str:
    """Expand a subject into a base prompt structure with random elements."""
    profession = random.choice(PROFESSIONS)
    action = random.choice(ACTIONS)
    location = random.choice(LOCATIONS)
    objects = random.choice(CONCRETE_OBJECTS)
    background = random.choice(BACKGROUNDS)
    foreground = random.choice(FOREGROUNDS)

    return f"""Subject: {subject}

A {profession} {action} {location}.
{objects}.
{background}.
{foreground}.

Channel: Stoic Modernized
Style: {STYLE_KEYWORDS}
Lighting: {LIGHTING}"""


async def refine_with_llamacpp(prompt: str, base_url: str, model: str) -> str | None:
    """Send prompt to llama.cpp for refinement."""
    payload = {
        "model": model,
        "prompt": f"{prompt}\n\nWrite a detailed image prompt based on the description above. Include all visual details.",
        "max_tokens": 400,
        "temperature": 0.8,
        "top_p": 0.95,
        "stop": ["\n\n\n", "End"],
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(f"{base_url}/completions", json=payload)
            response.raise_for_status()
            data = response.json()
            
            if data.get("choices") and data["choices"][0].get("text"):
                text = data["choices"][0]["text"].strip()
                # Remove any thinking tags
                text = text.replace("<think>", "").replace("</think>", "").strip()
                return text
    except Exception as e:
        print(f"Error calling llama.cpp: {e}", file=sys.stderr)
    
    return None


def main():
    parser = argparse.ArgumentParser(
        description="Generate Stoic Modernized image prompts using llama.cpp"
    )
    parser.add_argument(
        "subject",
        help="The subject/topic for the image prompt",
    )
    parser.add_argument(
        "--base-url",
        default="http://localhost:8080/v1",
        help="llama.cpp base URL (default: http://localhost:8080/v1)",
    )
    parser.add_argument(
        "--model",
        default="Qwen3.5-35B-A3B-Q8_0.gguf",
        help="Model name to use (default: Qwen3.5-35B-A3B-Q8_0.gguf)",
    )
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("Stoic Modernized Image Prompt Generator")
    print("=" * 60)
    print()
    print(f"Subject: {args.subject}")
    print()
    
    # Step 1: Expand subject into base structure
    expanded = expand_subject(args.subject)
    print("Step 1: Expanded base structure")
    print("-" * 60)
    print(expanded)
    print()
    
    # Step 2: Refine with llama.cpp
    print("Step 2: Refining with llama.cpp...")
    print("-" * 60)
    
    import asyncio
    final_prompt = asyncio.run(refine_with_llamacpp(expanded, args.base_url, args.model))
    
    if final_prompt:
        print("Final Prompt:")
        print("-" * 60)
        print(final_prompt)
        print()
        print("=" * 60)
        print("Ready to use in your image generation workflow")
        print("=" * 60)
    else:
        print("Failed to get response from llama.cpp")
        print("Make sure the llama.cpp server is running")
        sys.exit(1)


if __name__ == "__main__":
    main()
