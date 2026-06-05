"""
Regression tests for ReasoningBank memory response serialization.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from models.schemas import MemoryItemDetail  # noqa: E402


def test_memory_detail_response_accepts_generated_long_text():
    """Persisted LLM-generated memories should not fail response validation."""
    detail = MemoryItemDetail(
        title="Generated memory with full evidence",
        description="Evidence-calibrated interpretation. " * 30,
        content="Detailed mechanism and quantitative evidence. " * 80,
        is_from_success=True,
        source_task_id="REC_generated",
        created_at="2026-06-05T12:00:00",
        metadata={"source": "experiment_validated"},
    )

    assert detail.description.startswith("Evidence-calibrated interpretation.")
    assert len(detail.description) > 500
    assert len(detail.content) > 2000
