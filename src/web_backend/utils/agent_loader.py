"""
DESAgent Loader for Web Backend

Initializes and provides access to the DESAgent instance with
all required components (LLM clients, ReasoningBank, tools, etc.).
"""

import sys
import logging
from pathlib import Path
from typing import Optional

# Add parent directory to path for agent imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from agent.reasoningbank import (
    ReasoningBank,
    MemoryRetriever,
    MemoryExtractor,
    LLMJudge,
    RecommendationManager
)
from agent.des_agent import DESAgent
from agent.utils.llm_client import LLMClient
from agent.utils.embedding_client import EmbeddingClient
from agent.config import get_config

from web_backend.config import get_web_config

logger = logging.getLogger(__name__)


class AgentLoader:
    """
    Singleton loader for DESAgent

    This class initializes the DESAgent once and provides access
    to it throughout the web backend application lifecycle.
    """

    _instance: Optional['AgentLoader'] = None
    _agent: Optional[DESAgent] = None
    _rec_manager: Optional[RecommendationManager] = None

    def __new__(cls):
        """Singleton pattern"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def initialize(self) -> None:
        """
        Initialize DESAgent with all components.

        This should be called once during application startup.
        """
        if self._agent is not None:
            logger.warning("Agent already initialized, skipping...")
            return

        logger.info("Initializing DESAgent...")

        try:
            # Load configurations
            web_config = get_web_config()
            agent_config = get_config()

            # Create LLM clients from agent config
            llm_config = agent_config.get_llm_config("llm")
            agent_llm_config = agent_config.get_llm_config("agent_llm")

            llm_client = LLMClient(
                provider=llm_config["provider"],
                model=llm_config["model"],
                temperature=llm_config["temperature"],
                max_tokens=llm_config["max_tokens"],
                base_url=llm_config.get("api_base")
            )

            agent_llm_client = LLMClient(
                provider=agent_llm_config["provider"],
                model=agent_llm_config["model"],
                temperature=agent_llm_config["temperature"],
                max_tokens=agent_llm_config["max_tokens"],
                base_url=agent_llm_config.get("api_base")
            )

            logger.info(f"LLM initialized: {llm_config['provider']}/{llm_config['model']}")
            logger.info(f"Agent LLM initialized: {agent_llm_config['provider']}/{agent_llm_config['model']}")

            # Create embedding client
            embedding_config = agent_config.get_embedding_config()
            embedding_client = EmbeddingClient(
                provider=embedding_config["provider"],
                model=embedding_config["model"],
                base_url=embedding_config.get("api_base")
            )
            logger.info(f"Embedding client initialized: {embedding_config['provider']}/{embedding_config['model']}")

            # Get extractor configuration
            extractor_config = agent_config.get_extractor_config()
            extractor_temp = extractor_config.get("temperature", 1.0)

            # Get memory configuration
            memory_config = agent_config.get_memory_config()

            # Initialize ReasoningBank components
            # CRITICAL: Pass embedding_func to enable automatic embedding generation
            memory_bank = ReasoningBank(
                embedding_func=embedding_client.embed,  # Enable embedding for new memories
                max_items=memory_config.get("max_items", 1000)
            )
            retriever = MemoryRetriever(
                bank=memory_bank,
                embedding_func=embedding_client.embed  # Use embedding client's embed method
            )
            extractor = MemoryExtractor(llm_client, temperature=extractor_temp)
            judge = LLMJudge(llm_client)  # Not used in v1, but required

            # Initialize RecommendationManager
            rec_dir = web_config.get_recommendations_dir()
            rec_dir.mkdir(parents=True, exist_ok=True)
            self._rec_manager = RecommendationManager(storage_path=str(rec_dir))
            logger.info(f"RecommendationManager initialized: {rec_dir}")

            # Initialize DESAgent
            memory_dir = web_config.get_memory_dir()
            memory_dir.mkdir(parents=True, exist_ok=True)

            self._agent = DESAgent(
                llm_client=agent_llm_client,  # Use agent_llm for main reasoning
                reasoning_bank=memory_bank,
                retriever=retriever,
                extractor=extractor,
                judge=judge,
                rec_manager=self._rec_manager,
                corerag_client=None,  # TODO: Initialize if available
                largerag_client=None,  # TODO: Initialize if available
                config={
                    "memory": {
                        "auto_save": memory_config.get("auto_save", True),
                        "persist_path": str(memory_dir / "reasoning_bank.json"),
                        "retrieval_top_k": memory_config.get("retrieval_top_k", 3),
                        "min_similarity": memory_config.get("min_similarity", 0.0)
                    }
                }
            )

            logger.info("DESAgent initialized successfully")
            logger.info(f"Memory auto-save: {memory_config.get('auto_save')}")
            logger.info(f"Memory persist path: {memory_dir / 'reasoning_bank.json'}")

            # Try to load existing memory bank
            memory_file = memory_dir / "reasoning_bank.json"
            if memory_file.exists():
                try:
                    self._agent.memory.load(str(memory_file))
                    logger.info(f"Loaded existing memory bank: {len(self._agent.memory.memories)} memories")
                except Exception as e:
                    logger.warning(f"Failed to load existing memory bank: {e}")

        except Exception as e:
            logger.error(f"Failed to initialize DESAgent: {e}", exc_info=True)
            raise RuntimeError(f"Agent initialization failed: {str(e)}")

    def get_agent(self) -> DESAgent:
        """
        Get the initialized DESAgent instance.

        Returns:
            DESAgent instance

        Raises:
            RuntimeError: If agent not initialized
        """
        if self._agent is None:
            raise RuntimeError(
                "Agent not initialized. Call initialize() first."
            )
        return self._agent

    def get_rec_manager(self) -> RecommendationManager:
        """
        Get the RecommendationManager instance.

        Returns:
            RecommendationManager instance

        Raises:
            RuntimeError: If not initialized
        """
        if self._rec_manager is None:
            raise RuntimeError(
                "RecommendationManager not initialized. Call initialize() first."
            )
        return self._rec_manager


# Global loader instance
_loader: Optional[AgentLoader] = None


def get_agent_loader() -> AgentLoader:
    """Get agent loader singleton"""
    global _loader
    if _loader is None:
        _loader = AgentLoader()
    return _loader


def initialize_agent() -> None:
    """Initialize agent (call during app startup)"""
    loader = get_agent_loader()
    loader.initialize()


def get_agent() -> DESAgent:
    """Get initialized agent instance"""
    loader = get_agent_loader()
    return loader.get_agent()


def get_rec_manager() -> RecommendationManager:
    """Get recommendation manager instance"""
    loader = get_agent_loader()
    return loader.get_rec_manager()
