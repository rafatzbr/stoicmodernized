#!/usr/bin/env python3
"""Test script to verify prompt generation integration."""

import asyncio
import sys
from pathlib import Path

# Add the project root to the path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.prompt_generator import expand_subject, refine_with_llamacpp


async def test_prompt_generation():
    """Test the prompt generation flow."""
    test_subjects = [
        "staying calm when work feels urgent",
        "setting boundaries at work",
        "emotional detachment from chaos",
    ]
    
    base_url = "http://localhost:8080/v1"
    model = "/data/llama/Qwen3.6-35B-A3B-UD-Q8_K_XL.gguf"
    
    print("=" * 60)
    print("Testing Stoic Modernized Prompt Generation")
    print("=" * 60)
    print()
    
    for subject in test_subjects:
        print(f"\n--- Subject: {subject} ---")
        
        # Test expansion
        expanded = expand_subject(subject)
        print(f"Expanded:\n{expanded}")
        print()
        
        # Test refinement (only if llama.cpp is available)
        try:
            final = await refine_with_llamacpp(expanded, base_url, model)
            if final:
                print(f"Final Prompt:\n{final}")
            else:
                print("WARNING: llama.cpp returned empty prompt")
        except Exception as e:
            print(f"ERROR: {e}")
        
        print()


if __name__ == "__main__":
    asyncio.run(test_prompt_generation())
