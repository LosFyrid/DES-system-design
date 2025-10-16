"""
ReasoningBank: Memory-Augmented Agent Framework for DES Formulation Design

This package implements the ReasoningBank framework for storing and retrieving
reasoning strategies to guide DES (Deep Eutectic Solvent) formulation design.

Key Components:
- MemoryItem: Data structure for storing reasoning strategies
- ReasoningBank: Central memory management system
- MemoryRetriever: Embedding-based similarity search
- MemoryExtractor: Extract memories from trajectories
- LLMJudge: Evaluate trajectory outcomes (optional, not used in v1)

NEW (Async Experimental Feedback):
- ExperimentResult: Real experimental measurements (is_liquid_formed, solubility, properties)
- Recommendation: Persistent recommendation records with status tracking
- RecommendationManager: JSON-based storage and indexing for recommendations
- FeedbackProcessor: Process experimental feedback and extract data-driven memories
"""

from .memory import MemoryItem, MemoryQuery, Trajectory
from .memory_manager import ReasoningBank
from .retriever import MemoryRetriever, format_memories_for_prompt
from .extractor import MemoryExtractor
from .judge import LLMJudge
from .feedback import (
    ExperimentResult,
    Recommendation,
    RecommendationManager,
    FeedbackProcessor
)

__version__ = "0.2.0"  # Updated for async feedback support

__all__ = [
    # Core memory components
    "MemoryItem",
    "MemoryQuery",
    "Trajectory",
    "ReasoningBank",
    "MemoryRetriever",
    "MemoryExtractor",
    "LLMJudge",
    "format_memories_for_prompt",
    # NEW: Async feedback components
    "ExperimentResult",
    "Recommendation",
    "RecommendationManager",
    "FeedbackProcessor",
]
