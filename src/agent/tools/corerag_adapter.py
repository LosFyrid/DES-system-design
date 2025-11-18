"""
CoreRAG Adapter for DESAgent

This module adapts the CoreRAG ontology query interface to match what DESAgent expects.

Implements: DESToolProtocol
    - query(query_dict) -> Optional[Dict]
    - get_status() -> Dict

DESAgent expects:
    corerag_client.query(query_dict) -> Dict
    where query_dict contains: query, focus (optional list of topics)

CoreRAG provides:
    - Ontology-based structured knowledge retrieval
    - Multi-agent query workflow with entity matching
    - SPARQL query execution

This adapter bridges the gap and follows the standard tool interface.
"""

from typing import Dict, Optional, Any
import logging
import sys
from pathlib import Path
import atexit

# Add project/src and corerag to path so `agent`、`config` 等可被找到
import os
project_src_path = Path(__file__).resolve().parents[2]  # /app/src
corerag_path = project_src_path / "tools" / "corerag"
sys.path.insert(0, str(project_src_path))
sys.path.insert(0, str(corerag_path))

# Load .env file if exists (to get API keys)
from dotenv import load_dotenv
load_dotenv()

# Set PROJECT_ROOT for CoreRAG config
os.environ['PROJECT_ROOT'] = str(corerag_path) + os.sep

# Set OPENAI_API_KEY from DASHSCOPE_API_KEY if not set
if 'OPENAI_API_KEY' not in os.environ:
    if 'DASHSCOPE_API_KEY' in os.environ:
        os.environ['OPENAI_API_KEY'] = os.environ['DASHSCOPE_API_KEY']

logger = logging.getLogger(__name__)

# Avoid conflict with web_backend.config (module) which would shadow corerag/config namespace
existing_config = sys.modules.get("config")
if existing_config:
    cfg_file = getattr(existing_config, "__file__", "")
    if cfg_file and "web_backend/config.py" in cfg_file.replace("\\", "/"):
        sys.modules.pop("config", None)
        sys.modules.pop("config.settings", None)

# Import CoreRAG components
try:
    from autology_constructor.idea.query_team.query_manager import QueryManager
    from config.settings import ONTOLOGY_SETTINGS
    CORERAG_AVAILABLE = True
    _IMPORT_ERROR = None
    logger.info(
        "CoreRAG import OK | sys.path_head=%s | cwd=%s",
        list(sys.path)[:5],
        os.getcwd(),
    )
except Exception as e:  # broaden to capture any import-time failure
    _IMPORT_ERROR = e
    logger.warning(
        "CoreRAG dependencies not available: %s | sys.path=%s | cwd=%s",
        e, list(sys.path), os.getcwd(),
        exc_info=True
    )
    CORERAG_AVAILABLE = False
    QueryManager = None
    ONTOLOGY_SETTINGS = None


class CoreRAGAdapter:
    """
    Adapter class to make CoreRAG compatible with DESAgent interface.

    CoreRAG provides theoretical knowledge from chemistry ontologies using:
    - Entity extraction and matching
    - Ontology reasoning (OWL + SPARQL)
    - Multi-agent query workflow via QueryManager

    Usage:
        from agent.tools.corerag_adapter import CoreRAGAdapter

        # Initialize adapter
        corerag_client = CoreRAGAdapter()

        # Use in DESAgent
        agent = DESAgent(
            ...,
            corerag_client=corerag_client,
            ...
        )
    """

    def __init__(self, max_workers: int = 2):
        """
        Initialize CoreRAG adapter.

        Args:
            max_workers: Maximum number of worker threads for QueryManager (default: 2)
        """
        self.manager = None
        self.initialized = False

        if not CORERAG_AVAILABLE:
            logger.error(
                "CoreRAG dependencies not available. Ensure owlready2 and other dependencies are installed. "
                "import_error=%s | sys.path_head=%s | cwd=%s",
                _IMPORT_ERROR,
                sys.path[:5],
                os.getcwd(),
                exc_info=_IMPORT_ERROR
            )
            return

        try:
            logger.info("Initializing CoreRAG QueryManager...")
            logger.info(
                "CoreRAGAdapter init | cwd=%s | sys.path_head=%s",
                os.getcwd(), sys.path[:5]
            )

            # Initialize QueryManager with ontology settings
            self.manager = QueryManager(
                max_workers=max_workers,
                ontology_settings=ONTOLOGY_SETTINGS,
                staggered_start=False  # No need for staggered start with single queries
            )

            # Start the dispatcher thread
            self.manager.start()

            self.initialized = True
            logger.info("CoreRAG adapter initialized successfully")

            # Register cleanup on exit
            atexit.register(self._cleanup)

        except Exception as e:
            logger.error(f"Failed to initialize CoreRAG: {e}", exc_info=True)
            self.initialized = False
            self.manager = None

    def query(self, query_dict: Dict[str, Any]) -> Optional[Dict]:
        """
        Query CoreRAG for theoretical knowledge.

        Args:
            query_dict: Query parameters with keys:
                - query (str): Query text
                - focus (list, optional): List of focus topics
                  (e.g., ["hydrogen_bonding", "component_selection"])
                - priority (str, optional): Query priority ("normal", "high", "low")

        Returns:
            Dict containing:
                - query: Original query text
                - answer: Answer from ontology reasoning
                - entities: Extracted entities from query
                - tool_calls: Tools used in reasoning
                - formatted_text: Human-readable formatted results
                - num_results: Number of relevant entities/facts

            Returns None if CoreRAG is not initialized or query fails.

        Example:
            query_dict = {
                "query": "What are the key principles for dissolving cellulose using DES?",
                "focus": ["hydrogen_bonding", "component_selection", "molar_ratio"]
            }
            result = adapter.query(query_dict)
        """
        if not self.initialized or self.manager is None:
            logger.error("CoreRAG not initialized. Cannot query.")
            return None

        try:
            # Extract parameters
            query_text = query_dict.get("query", "")
            focus = query_dict.get("focus", [])
            priority = query_dict.get("priority", "normal")

            if not query_text:
                logger.warning("Empty query text provided")
                return None

            # Prepare query context
            query_context = {
                "originating_team": "DESAgent",
                "originating_agent": "CoreRAGAdapter",
                "focus_topics": focus
            }

            logger.info(f"Submitting query to CoreRAG: '{query_text[:100]}...'")

            # Submit query and get Future
            future = self.manager.submit_query(
                query_text=query_text,
                query_context=query_context,
                priority=priority
            )

            # Wait for result (blocks until complete)
            logger.info("Waiting for CoreRAG result...")
            state_result = future.result(timeout=120)  # 2 minute timeout

            logger.info("CoreRAG query completed")

            # Extract and format result
            result = self._extract_result(query_text, state_result, focus)

            return result

        except Exception as e:
            logger.error(f"CoreRAG query failed: {e}", exc_info=True)
            return None

    def _extract_result(self, query_text: str, state_result: Dict, focus: list) -> Dict:
        """
        Extract and format result from QueryManager state.

        Args:
            query_text: Original query text
            state_result: State dict returned by QueryManager
            focus: Focus topics

        Returns:
            Formatted result dict
        """
        # Extract key information from state
        answer = state_result.get("answer", "")
        normalized_query = state_result.get("normalized_query", {})
        entities = normalized_query.get("entities", [])
        validation_report = state_result.get("validation_report", {})
        tried_tool_calls = state_result.get("tried_tool_calls", [])

        # Format entities
        entity_names = [e.get("name", "") for e in entities if isinstance(e, dict)]

        # Count successful tool calls
        num_results = len(tried_tool_calls)

        # Format the result
        formatted_text = self._format_theory_knowledge(
            query_text, answer, entity_names, tried_tool_calls, focus
        )

        return {
            "query": query_text,
            "answer": answer,
            "entities": entity_names,
            "tool_calls": tried_tool_calls,
            "validation_status": validation_report.get("classification", "unknown"),
            "formatted_text": formatted_text,
            "num_results": num_results,
            "raw_state": state_result  # Include raw state for advanced use
        }

    def _format_theory_knowledge(
        self,
        query_text: str,
        answer: str,
        entities: list,
        tool_calls: list,
        focus: list = None
    ) -> str:
        """
        Format theoretical knowledge for display in agent prompt.

        Args:
            query_text: Original query
            answer: Answer from CoreRAG
            entities: List of extracted entities
            tool_calls: List of tool calls made
            focus: Focus topics

        Returns:
            Formatted string suitable for LLM context
        """
        formatted = "## Theoretical Knowledge (from CoreRAG Ontology)\n\n"
        formatted += f"**Query:** {query_text}\n\n"

        if focus:
            formatted += f"**Focus Areas:** {', '.join(focus)}\n\n"

        if entities:
            formatted += f"**Key Entities:** {', '.join(entities[:10])}{'...' if len(entities) > 10 else ''}\n\n"

        if answer:
            formatted += f"**Ontology-Based Answer:**\n{answer}\n\n"
        else:
            formatted += "**Ontology-Based Answer:** No specific answer generated\n\n"

        if tool_calls:
            formatted += f"**Reasoning Tools Used:** {len(tool_calls)} ontology operations\n"

        return formatted

    def get_status(self) -> Dict[str, Any]:
        """
        Get status information about the CoreRAG system.

        Returns:
            Dict with status information
        """
        if not self.initialized or self.manager is None:
            return {
                "status": "not_initialized",
                "message": "CoreRAG adapter not initialized"
            }

        try:
            # Check if manager is running
            cache_stats = self.manager.query_queue_manager.cache.cache

            return {
                "status": "ready",
                "message": "CoreRAG QueryManager is running",
                "stats": {
                    "max_workers": self.manager.executor._max_workers,
                    "cached_queries": len(cache_stats),
                    "ontology_loaded": True
                }
            }
        except Exception as e:
            return {
                "status": "error",
                "message": f"Status check failed: {str(e)}"
            }

    def _cleanup(self):
        """Cleanup resources when adapter is destroyed."""
        if self.manager:
            try:
                logger.info("Stopping CoreRAG QueryManager...")
                self.manager.stop()
                logger.info("CoreRAG QueryManager stopped")
            except Exception as e:
                logger.error(f"Error stopping QueryManager: {e}")

    def __del__(self):
        """Destructor to ensure cleanup."""
        self._cleanup()


# Convenience function
def create_corerag_adapter(max_workers: int = 2) -> CoreRAGAdapter:
    """
    Convenience function to create a CoreRAG adapter.

    Args:
        max_workers: Maximum number of worker threads (default: 2)

    Returns:
        CoreRAGAdapter instance

    Usage:
        from agent.tools.corerag_adapter import create_corerag_adapter

        corerag_client = create_corerag_adapter()
        agent = DESAgent(..., corerag_client=corerag_client, ...)
    """
    return CoreRAGAdapter(max_workers=max_workers)


# For testing
if __name__ == "__main__":
    # Load environment variables from .env
    from dotenv import load_dotenv
    load_dotenv()

    # Import validation function
    try:
        from base import validate_tool_interface
    except ImportError:
        # Fallback if running directly
        def validate_tool_interface(tool):
            return hasattr(tool, 'query') and hasattr(tool, 'get_status')

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # Test adapter
    print("Testing CoreRAG Adapter...")
    print("="*60)

    adapter = CoreRAGAdapter(max_workers=1)

    # Validate interface
    print(f"\n✓ Implements DESToolProtocol: {validate_tool_interface(adapter)}")

    # Check status
    status = adapter.get_status()
    print(f"\n✓ Status: {status}")

    if status["status"] == "ready":
        # Test query
        query_dict = {
            "query": "What are the key principles for dissolving cellulose using DES?",
            "focus": ["hydrogen_bonding", "component_selection"]
        }

        print(f"\nTest query: {query_dict['query']}")
        print("Executing query (this may take a minute)...")

        result = adapter.query(query_dict)

        if result:
            print(f"\n✓ Query successful")
            print(f"  - Answer: {result.get('answer', '')[:200]}...")
            print(f"  - Entities: {result.get('entities', [])[:5]}")
            print(f"  - Tool calls: {result.get('num_results', 0)}")
            print(f"\nFormatted output:\n{result['formatted_text']}")
        else:
            print("\n✗ Query failed")
    else:
        print(f"\n✗ CoreRAG not ready: {status.get('message', 'Unknown error')}")

    # Cleanup
    print("\nCleaning up...")
    adapter._cleanup()
    print("Done!")
