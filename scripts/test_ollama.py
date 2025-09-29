#!/usr/bin/env python3
"""
Quick test script to verify Ollama is working with our LLM provider
"""
import asyncio
import sys
import os

# Add parent directory to path so we can import from app
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.llm_provider import get_llm_provider


async def test_ollama():
    """Test Ollama integration"""
    print("🧪 Testing Ollama Integration")
    print("=" * 50)
    print()

    # Get LLM provider
    llm = get_llm_provider()
    print(f"✅ Provider detected: {llm.provider}")
    print()

    # Test prompt
    prompt = """Summarize this daily standup:

**Alice (Developer):**
- Yesterday: Completed login API endpoint, fixed 2 bugs in user service
- Today: Working on password reset flow, code review for Bob's PR
- Blockers: Waiting for design mockups from design team

**Bob (Developer):**
- Yesterday: Implemented OAuth integration, wrote unit tests
- Today: Refactoring database layer, meeting with product team
- Blockers: None

**Charlie (Developer):**
- Yesterday: Deployed payment gateway updates to staging
- Today: Testing new checkout flow, fixing production bug
- Blockers: Need access to production logs

Provide a concise summary with: completed work, today's focus, and blockers."""

    print("📝 Test Prompt:")
    print("-" * 50)
    print(prompt[:200] + "...")
    print()

    print("⏳ Generating response...")
    print()

    try:
        result = await llm.generate_completion(
            prompt=prompt,
            system_prompt="You are an AI Scrum Master assistant. Provide concise, actionable summaries.",
            max_tokens=500,
            temperature=0.3
        )

        print("✅ Success!")
        print("=" * 50)
        print()
        print("📄 RESPONSE:")
        print("-" * 50)
        print(result['response'])
        print("-" * 50)
        print()
        print(f"📊 Stats:")
        print(f"  - Model: {result['model']}")
        print(f"  - Provider: {result['provider']}")
        print(f"  - Tokens: {result['tokens_used']}")
        print(f"  - Cost: ${llm.estimate_cost(result['tokens_used']):.4f}")
        print()
        print("🎉 Ollama is working perfectly!")

    except Exception as e:
        print(f"❌ Error: {e}")
        print()
        print("Make sure Ollama is running:")
        print("  ollama serve")
        return False

    return True


if __name__ == "__main__":
    success = asyncio.run(test_ollama())
    sys.exit(0 if success else 1)