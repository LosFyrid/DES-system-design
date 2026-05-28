"""
Unit tests for ReasoningBank core components

Run with: python -m pytest test_reasoningbank.py -v
"""

import pytest
import tempfile
import os
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from agent.reasoningbank import (
    MemoryItem,
    MemoryQuery,
    Trajectory,
    ReasoningBank,
    MemoryRetriever,
)


# Mock embedding function
def mock_embedding(text: str) -> list:
    import hashlib
    hash_val = int(hashlib.md5(text.encode()).hexdigest(), 16)
    return [(hash_val >> i) % 100 / 100.0 for i in range(128)]


class TestMemoryItem:
    """Test MemoryItem data structure"""

    def test_create_memory_item(self):
        """Test creating a valid memory item"""
        memory = MemoryItem(
            title="Test Memory",
            description="This is a test",
            content="Test content for memory item"
        )

        assert memory.title == "Test Memory"
        assert memory.description == "This is a test"
        assert memory.is_from_success == True

    def test_memory_validation(self):
        """Test that empty fields raise errors"""
        with pytest.raises(ValueError):
            MemoryItem(title="", description="test", content="test")

        with pytest.raises(ValueError):
            MemoryItem(title="test", description="", content="test")

        with pytest.raises(ValueError):
            MemoryItem(title="test", description="test", content="")

    def test_memory_serialization(self):
        """Test to_dict and from_dict"""
        memory = MemoryItem(
            title="Test",
            description="Description",
            content="Content",
            source_task_id="task_001",
            is_from_success=False
        )

        # Serialize
        data = memory.to_dict()
        assert data["title"] == "Test"
        assert data["is_from_success"] == False

        # Deserialize
        reconstructed = MemoryItem.from_dict(data)
        assert reconstructed.title == memory.title
        assert reconstructed.is_from_success == memory.is_from_success

    def test_memory_deserialization_uses_liquid_formation_metadata(self):
        """Experiment memories derive success/failure from DES liquid formation."""
        data = {
            "title": "No Liquid Formed",
            "description": "Description",
            "content": "Content",
            "source_task_id": "REC_001",
            "is_from_success": True,
            "metadata": {"is_liquid_formed": False},
        }

        reconstructed = MemoryItem.from_dict(data)

        assert reconstructed.is_from_success is False

    def test_prompt_formatting(self):
        """Test prompt string generation"""
        memory = MemoryItem(
            title="Test Strategy",
            description="Test desc",
            content="This is the reasoning content."
        )

        prompt_str = memory.to_prompt_string()
        assert "Test Strategy" in prompt_str
        assert "This is the reasoning content" in prompt_str


class TestReasoningBank:
    """Test ReasoningBank memory manager"""

    def test_create_bank(self):
        """Test creating a memory bank"""
        bank = ReasoningBank(embedding_func=mock_embedding, max_items=10)
        assert len(bank) == 0
        assert bank.max_items == 10

    def test_add_memory(self):
        """Test adding memories"""
        bank = ReasoningBank(embedding_func=mock_embedding)

        memory = MemoryItem(
            title="Memory 1",
            description="First memory",
            content="Content 1"
        )

        bank.add_memory(memory)
        assert len(bank) == 1

        # Check embedding was computed
        retrieved = bank.get_all_memories()[0]
        assert retrieved.embedding is not None

    def test_max_items_limit(self):
        """Test that bank enforces max_items limit"""
        bank = ReasoningBank(embedding_func=mock_embedding, max_items=3)

        # Add 5 memories
        for i in range(5):
            memory = MemoryItem(
                title=f"Memory {i}",
                description=f"Desc {i}",
                content=f"Content {i}"
            )
            bank.add_memory(memory)

        # Should only have 3 (oldest removed)
        assert len(bank) == 3

        # First two should be removed
        titles = [m.title for m in bank.get_all_memories()]
        assert "Memory 0" not in titles
        assert "Memory 1" not in titles
        assert "Memory 4" in titles

    def test_filter_memories(self):
        """Test filtering by metadata"""
        bank = ReasoningBank(embedding_func=mock_embedding)

        # Add success and failure memories
        bank.add_memory(MemoryItem(
            title="Success 1",
            description="desc",
            content="content",
            is_from_success=True
        ))

        bank.add_memory(MemoryItem(
            title="Failure 1",
            description="desc",
            content="content",
            is_from_success=False
        ))

        # Filter
        successes = bank.filter_memories({"is_from_success": True})
        failures = bank.filter_memories({"is_from_success": False})

        assert len(successes) == 1
        assert len(failures) == 1
        assert successes[0].title == "Success 1"
        assert failures[0].title == "Failure 1"

    def test_save_load(self):
        """Test persistence"""
        bank = ReasoningBank(embedding_func=mock_embedding)

        # Add memories
        for i in range(3):
            bank.add_memory(MemoryItem(
                title=f"Memory {i}",
                description=f"Desc {i}",
                content=f"Content {i}"
            ))

        # Save to temp file
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as f:
            temp_path = f.name

        try:
            bank.save(temp_path)

            # Load into new bank
            new_bank = ReasoningBank(embedding_func=mock_embedding)
            new_bank.load(temp_path)

            # Verify
            assert len(new_bank) == 3
            titles = [m.title for m in new_bank.get_all_memories()]
            assert "Memory 0" in titles
            assert "Memory 2" in titles

        finally:
            # Cleanup
            if os.path.exists(temp_path):
                os.remove(temp_path)


class TestMemoryRetriever:
    """Test MemoryRetriever"""

    def test_create_retriever(self):
        """Test creating retriever"""
        bank = ReasoningBank(embedding_func=mock_embedding)
        retriever = MemoryRetriever(bank, embedding_func=mock_embedding)

        assert retriever.bank == bank

    def test_retrieval(self):
        """Test memory retrieval"""
        bank = ReasoningBank(embedding_func=mock_embedding)

        # Add memories with different content
        bank.add_memory(MemoryItem(
            title="Hydrogen Bonding Strategy",
            description="About H-bonds",
            content="Focus on hydrogen bonding for cellulose"
        ))

        bank.add_memory(MemoryItem(
            title="Temperature Control",
            description="About temperature",
            content="Consider viscosity at low temperatures"
        ))

        bank.add_memory(MemoryItem(
            title="Component Selection",
            description="About components",
            content="Select bio-based HBD and HBA"
        ))

        # Create retriever
        retriever = MemoryRetriever(bank, embedding_func=mock_embedding)

        # Query for H-bond related memory
        query = MemoryQuery(
            query_text="What should I consider for dissolving cellulose?",
            top_k=2,
            min_similarity=0.0
        )

        retrieved = retriever.retrieve(query)

        # Should get 2 memories
        assert len(retrieved) == 2

        # Check that we get memories (exact order depends on embedding)
        titles = [m.title for m in retrieved]
        assert len(titles) == 2

    def test_retrieval_with_filters(self):
        """Test retrieval with metadata filters"""
        bank = ReasoningBank(embedding_func=mock_embedding)

        # Add memories with different success status
        bank.add_memory(MemoryItem(
            title="Success 1",
            description="success",
            content="This worked",
            is_from_success=True
        ))

        bank.add_memory(MemoryItem(
            title="Failure 1",
            description="failure",
            content="This failed",
            is_from_success=False
        ))

        retriever = MemoryRetriever(bank, embedding_func=mock_embedding)

        # Query with filter
        query = MemoryQuery(
            query_text="test query",
            top_k=5,
            filters={"is_from_success": True}
        )

        retrieved = retriever.retrieve(query)

        # Should only get success memory
        assert len(retrieved) == 1
        assert retrieved[0].title == "Success 1"


class TestTrajectory:
    """Test Trajectory data structure"""

    def test_create_trajectory(self):
        """Test creating a trajectory"""
        traj = Trajectory(
            task_id="task_001",
            task_description="Test task",
            steps=[
                {"action": "step1", "reasoning": "reason1"},
                {"action": "step2", "reasoning": "reason2"}
            ],
            outcome="success",
            final_result={"formulation": {}},
            metadata={"target_material": "cellulose"}
        )

        assert traj.task_id == "task_001"
        assert len(traj.steps) == 2
        assert traj.outcome == "success"

    def test_trajectory_serialization(self):
        """Test trajectory to/from dict"""
        traj = Trajectory(
            task_id="task_001",
            task_description="Test",
            steps=[],
            outcome="success",
            final_result={},
            metadata={}
        )

        # Serialize
        data = traj.to_dict()
        assert data["task_id"] == "task_001"

        # Deserialize
        reconstructed = Trajectory.from_dict(data)
        assert reconstructed.task_id == traj.task_id


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v"])
