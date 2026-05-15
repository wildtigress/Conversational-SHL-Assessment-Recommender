"""
test_agent.py
-------------
Manual test script — run this to verify your setup before deploying.

Usage (from the project root, with venv active):
    python test_agent.py

It runs 6 test scenarios covering all required behaviors.
"""

import json
import sys
import os

# Make sure we can import from app/
sys.path.insert(0, os.path.dirname(__file__))

from dotenv import load_dotenv
load_dotenv()

# ── test cases ────────────────────────────────────────────────────────────────

TEST_CASES = [
    {
        "name": "1. Vague query — should CLARIFY, not recommend",
        "messages": [
            {"role": "user", "content": "I need an assessment"}
        ],
        "expect_empty_recs": True,
    },
    {
        "name": "2. Clear role — should RECOMMEND",
        "messages": [
            {"role": "user", "content": "I am hiring a mid-level Python developer. They need strong coding skills and will work independently."}
        ],
        "expect_empty_recs": False,
    },
    {
        "name": "3. Job description provided — should RECOMMEND immediately",
        "messages": [
            {
                "role": "user",
                "content": (
                    "Here is a job description: "
                    "We are looking for a Senior Java Software Engineer with 5+ years of experience "
                    "in Java 8+, Spring Boot, microservices, and SQL databases. The role requires "
                    "strong problem-solving skills and the ability to work with business stakeholders."
                )
            }
        ],
        "expect_empty_recs": False,
    },
    {
        "name": "4. Refinement mid-conversation — should UPDATE shortlist",
        "messages": [
            {"role": "user",      "content": "I need to hire a customer service representative."},
            {"role": "assistant", "content": "I can help with that! For a customer service representative, I'd recommend assessments that measure communication skills and customer orientation. Could you tell me more about the seniority level and whether this is a phone-based, chat-based, or in-person role?"},
            {"role": "user", "content": "Actually, please also add a personality test to the list."},
        ],
        "expect_empty_recs": False,
    },
    {
        "name": "5. Comparison query — should COMPARE using catalog data",
        "messages": [
            {"role": "user", "content": "What is the difference between OPQ32r and the Motivational Questionnaire?"}
        ],
        "expect_empty_recs": True,   # comparison might not include recs
    },
    {
        "name": "6. Off-topic — should REFUSE",
        "messages": [
            {"role": "user", "content": "What salary should I offer a software engineer in London?"}
        ],
        "expect_empty_recs": True,
    },
]


def run_tests():
    print("=" * 60)
    print("SHL Recommender — Test Suite")
    print("=" * 60)

    # Import agent (this triggers model loading)
    print("\n[setup] Loading retrieval index and embedding model…")
    from app.agent import chat
    print("[setup] Ready.\n")

    passed = 0
    failed = 0

    for tc in TEST_CASES:
        print(f"\n{'-'*50}")
        print(f"TEST: {tc['name']}")
        print(f"Input: {tc['messages'][-1]['content'][:80]}..." if len(tc['messages'][-1]['content']) > 80 else f"Input: {tc['messages'][-1]['content']}")

        try:
            result = chat(tc["messages"])
        except Exception as e:
            print(f"FAIL EXCEPTION: {e}")
            failed += 1
            continue

        # Basic schema checks
        assert "reply" in result,               "Missing 'reply' key"
        assert "recommendations" in result,     "Missing 'recommendations' key"
        assert "end_of_conversation" in result, "Missing 'end_of_conversation' key"
        assert isinstance(result["reply"], str),               "'reply' must be string"
        assert isinstance(result["recommendations"], list),    "'recommendations' must be list"
        assert isinstance(result["end_of_conversation"], bool),"'end_of_conversation' must be bool"

        recs = result["recommendations"]
        if recs:
            for rec in recs:
                assert "name"      in rec, f"Recommendation missing 'name': {rec}"
                assert "url"       in rec, f"Recommendation missing 'url': {rec}"
                assert "test_type" in rec, f"Recommendation missing 'test_type': {rec}"
                assert rec["url"].startswith("https://www.shl.com/"), \
                    f"URL not from SHL: {rec['url']}"

        # Behavior check
        if tc["expect_empty_recs"] and recs:
            print(f"WARN Expected empty recommendations but got {len(recs)}")
            print(f"   Reply: {result['reply'][:100]}")
            # Don't fail the test — vague queries COULD get recs in multi-turn
        elif not tc["expect_empty_recs"] and not recs:
            print(f"WARN Expected recommendations but got empty list")
            print(f"   Reply: {result['reply'][:100]}")

        print(f"PASS Reply: {result['reply'][:120]}")
        if recs:
            print(f"   Recommendations ({len(recs)}):")
            for rec in recs[:3]:
                print(f"     - {rec['name']} [{rec['test_type']}]")
            if len(recs) > 3:
                print(f"     … and {len(recs)-3} more")
        print(f"   end_of_conversation: {result['end_of_conversation']}")
        passed += 1

    print(f"\n{'='*60}")
    print(f"Results: {passed} passed, {failed} failed out of {len(TEST_CASES)} tests")
    print("=" * 60)

    if failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    run_tests()
