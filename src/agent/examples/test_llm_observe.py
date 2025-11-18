"""
Test script for LLM-based OBSERVE phase

This script tests the new LLM-based observation analysis.
"""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from agent.prompts import (
    OBSERVE_PROMPT,
    format_action_result_for_observe,
    parse_observe_output
)


def test_observe_prompt_formatting():
    """Test OBSERVE prompt formatting"""
    print("=" * 60)
    print("Testing OBSERVE Prompt Formatting")
    print("=" * 60)

    # Mock action result
    action_result = {
        "action": "query_literature",
        "success": True,
        "summary": "Retrieved 10 papers on cellulose-DES systems",
        "data": {"papers": ["paper1", "paper2"]}
    }

    # Mock knowledge state
    knowledge_state = {
        "memories_retrieved": True,
        "memories": [{"title": "Test memory"}],
        "num_theory_queries": 1,
        "failed_theory_attempts": 0,
        "num_literature_queries": 1,
        "failed_literature_attempts": 0,
        "formulation_candidates": [],
        "observations": []
    }

    # Format action result
    formatted_result = format_action_result_for_observe(
        "query_literature",
        action_result,
        knowledge_state
    )

    print("\n[Formatted Action Result]")
    print(formatted_result)

    # Build full prompt
    prompt = OBSERVE_PROMPT.format(
        task_description="Design DES to dissolve cellulose",
        target_material="cellulose",
        target_temperature=25,
        iteration=2,
        max_iterations=8,
        progress_pct=25,
        stage="Early",
        action="query_literature",
        success=True,
        action_result_summary=formatted_result,
        has_memories=True,
        num_memories=1,
        num_theory=1,
        failed_theory=0,
        num_literature=1,
        failed_literature=0,
        num_formulations=0,
        num_observations=1,
        recent_observations="1. Previous action completed"
    )

    print("\n[Full OBSERVE Prompt] (first 500 chars)")
    print(prompt[:500] + "...")
    print(f"\nPrompt length: {len(prompt)} characters")


def test_parse_observe_output():
    """Test parsing of LLM OBSERVE output"""
    print("\n" + "=" * 60)
    print("Testing OBSERVE Output Parsing")
    print("=" * 60)

    # Mock LLM output
    mock_output = """{
    "summary": "Retrieved 10 literature papers on cellulose-DES systems. Glycerol-based DES dominate (60%).",
    "knowledge_updated": ["literature"],
    "key_insights": [
        "Glycerol-based DES show 60% prevalence in recent publications",
        "Optimal molar ratios consistently reported as 1:2 to 1:3",
        "Most studies focus on 40-80°C range; only 2/10 papers report 25°C data"
    ],
    "information_gaps": [
        "Lack low-temperature (25°C) solubility data",
        "No viscosity measurements found in retrieved literature"
    ],
    "information_sufficient": false,
    "recommended_next_action": "query_theory",
    "recommendation_reasoning": "Need theoretical understanding of why glycerol outperforms urea at low temperature"
}"""

    parsed = parse_observe_output(mock_output)

    print("\n[Parsed Observation]")
    print(f"Summary: {parsed['summary']}")
    print(f"Knowledge Updated: {parsed['knowledge_updated']}")
    print(f"Key Insights ({len(parsed['key_insights'])}):")
    for i, insight in enumerate(parsed['key_insights'], 1):
        print(f"  {i}. {insight}")
    print(f"Information Gaps ({len(parsed['information_gaps'])}):")
    for i, gap in enumerate(parsed['information_gaps'], 1):
        print(f"  {i}. {gap}")
    print(f"Information Sufficient: {parsed['information_sufficient']}")
    print(f"Recommended Next Action: {parsed['recommended_next_action']}")
    print(f"Reasoning: {parsed['recommendation_reasoning']}")


def test_fallback_parsing():
    """Test fallback parsing for malformed output"""
    print("\n" + "=" * 60)
    print("Testing Fallback Parsing (Malformed JSON)")
    print("=" * 60)

    malformed_output = "This is not valid JSON"

    parsed = parse_observe_output(malformed_output)

    print("\n[Fallback Observation]")
    print(f"Summary: {parsed['summary']}")
    print(f"Recommended Action: {parsed['recommended_next_action']}")
    print("\n✓ Fallback parsing worked correctly")


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("LLM-Based OBSERVE Phase - Test Suite")
    print("=" * 60)

    try:
        test_observe_prompt_formatting()
        test_parse_observe_output()
        test_fallback_parsing()

        print("\n" + "=" * 60)
        print("✓ All tests passed!")
        print("=" * 60)

    except Exception as e:
        print(f"\n✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
