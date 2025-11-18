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

# Prepare a dedicated `config` package for CoreRAG so that
# `from config.settings import ...` in corerag code always resolves
# to /app/src/tools/corerag/config/settings.py, even if there is a
# top-level config.py elsewhere (e.g., web_backend/config.py).
import importlib, importlib.util, types

# Remove any pre-loaded top-level `config` module
sys.modules.pop("config", None)
sys.modules.pop("config.settings", None)

try:
    config_dir = corerag_path / "config"
    settings_path = config_dir / "settings.py"

    # Create a lightweight package module for `config`
    config_pkg = types.ModuleType("config")
    config_pkg.__path__ = [str(config_dir)]
    sys.modules["config"] = config_pkg

    # Load settings.py explicitly as `config.settings`
    spec = importlib.util.spec_from_file_location("config.settings", settings_path)
    settings_mod = importlib.util.module_from_spec(spec)
    sys.modules["config.settings"] = settings_mod
    assert spec.loader is not None
    spec.loader.exec_module(settings_mod)
except Exception:
    # Any failure here will be surfaced by the subsequent import below
    pass

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

# Load tool timeout configuration from ReasoningBank config
try:
    from agent.config import get_config

    _tools_cfg = get_config().get_tools_config()
    _corerag_cfg = _tools_cfg.get("corerag", {})
    _CORERAG_TIMEOUT_SECONDS = int(_corerag_cfg.get("timeout", 600))
except Exception as e:
    logger.warning(
        "Failed to load CoreRAG timeout from config: %s. Using default 600s.",
        e,
    )
    _CORERAG_TIMEOUT_SECONDS = 600

# Allow environment variable to override config timeout if set
_timeout_env = os.getenv("CORERAG_TIMEOUT_SECONDS")
if _timeout_env:
    try:
        _CORERAG_TIMEOUT_SECONDS = int(_timeout_env)
    except ValueError:
        logger.warning(
            "Invalid CORERAG_TIMEOUT_SECONDS value '%s', keeping %s seconds.",
            _timeout_env,
            _CORERAG_TIMEOUT_SECONDS,
        )


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
            logger.info(
                "Waiting for CoreRAG result (timeout=%ss)...",
                _CORERAG_TIMEOUT_SECONDS,
            )
            # CoreRAG workflows can legitimately take several minutes
            # (multi-step tool calls + retries). Use the timeout from
            # config/tools.corerag.timeout, overridable via env.
            state_result = future.result(timeout=_CORERAG_TIMEOUT_SECONDS)

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
        # Prefer the fully formatted result from CoreRAG (FormattedResult schema).
        formatted_results = state_result.get("formatted_results")
        if isinstance(formatted_results, dict) and formatted_results:
            return formatted_results

        # Fallback: if formatter failed or is missing, expose the lower-level
        # query_results so DESAgent still has some usable information.
        query_results = state_result.get("query_results")
        if isinstance(query_results, dict) and query_results:
            return query_results

        # Last-resort fallback: return an empty dict to signal "no theory available".
        return {}

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
