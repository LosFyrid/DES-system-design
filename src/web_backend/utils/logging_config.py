"""
Unified Logging Configuration for DES System

Provides centralized logging setup with:
- Module-based log file separation (web_backend, agent, largerag, corerag, root)
- Timestamped log files
- Rotating file handlers (100MB max, 5 backups)
- Simultaneous stdout output for Docker logs
"""

import logging
import logging.handlers
from pathlib import Path
from datetime import datetime
from typing import Optional


class LoggerFilter(logging.Filter):
    """
    Filter logs by logger name prefix.

    Only allows records whose logger name matches specified prefixes.
    """

    def __init__(self, prefixes: list[str], exact_names: Optional[list[str]] = None):
        """
        Args:
            prefixes: List of logger name prefixes to match (e.g., ['agent.', 'api.'])
            exact_names: List of exact logger names to match (e.g., ['__main__', 'config'])
        """
        super().__init__()
        self.prefixes = prefixes
        self.exact_names = exact_names or []

    def filter(self, record: logging.LogRecord) -> bool:
        """
        Check if record's logger name matches any prefix or exact name.
        """
        # Check exact matches first
        if record.name in self.exact_names:
            return True

        # Check prefix matches
        for prefix in self.prefixes:
            if record.name.startswith(prefix):
                return True

        return False


class ExcludeFilter(logging.Filter):
    """
    Exclude logs that match other module filters (for root logger fallback).
    """

    def __init__(self, exclude_prefixes: list[str], exclude_exact: Optional[list[str]] = None):
        super().__init__()
        self.exclude_prefixes = exclude_prefixes
        self.exclude_exact = exclude_exact or []

    def filter(self, record: logging.LogRecord) -> bool:
        """
        Return False if record matches any exclude pattern (inverse logic).
        """
        # Exclude exact matches
        if record.name in self.exclude_exact:
            return False

        # Exclude prefix matches
        for prefix in self.exclude_prefixes:
            if record.name.startswith(prefix):
                return False

        return True


def setup_logging(log_dir: Path, level: str = "INFO") -> None:
    """
    Configure centralized logging with module-based file separation.

    Creates 5 log files:
    - web_backend_{timestamp}.log: API endpoints, services, utilities
    - agent_{timestamp}.log: Agent reasoning, ReasoningBank, tool adapters
    - largerag_{timestamp}.log: Vector search, document processing
    - corerag_{timestamp}.log: Ontology queries, SPARQL execution
    - root_{timestamp}.log: Uncategorized logs, third-party libraries

    Args:
        log_dir: Directory to store log files
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)

    Example:
        >>> from pathlib import Path
        >>> setup_logging(Path("/app/logs"), level="INFO")
        >>> logger = logging.getLogger("agent.des_agent")
        >>> logger.info("This goes to agent_{timestamp}.log")
    """
    # Ensure log directory exists
    log_dir.mkdir(parents=True, exist_ok=True)

    # Generate timestamp for this session
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Common formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # Convert level string to logging constant
    log_level = getattr(logging, level.upper(), logging.INFO)

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Clear any existing handlers (avoid duplicates)
    root_logger.handlers.clear()

    # ===== 1. StreamHandler for stdout (Docker logs) =====
    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # ===== 2. Web Backend Handler =====
    web_backend_file = log_dir / f"web_backend_{timestamp}.log"
    web_backend_handler = logging.handlers.RotatingFileHandler(
        web_backend_file,
        maxBytes=100 * 1024 * 1024,  # 100MB
        backupCount=5,
        encoding='utf-8'
    )
    web_backend_handler.setLevel(log_level)
    web_backend_handler.setFormatter(formatter)
    web_backend_handler.addFilter(LoggerFilter(
        prefixes=['api.', 'services.', 'utils.'],
        exact_names=['__main__', 'config']
    ))
    root_logger.addHandler(web_backend_handler)

    # ===== 3. Agent Handler =====
    agent_file = log_dir / f"agent_{timestamp}.log"
    agent_handler = logging.handlers.RotatingFileHandler(
        agent_file,
        maxBytes=100 * 1024 * 1024,
        backupCount=5,
        encoding='utf-8'
    )
    agent_handler.setLevel(log_level)
    agent_handler.setFormatter(formatter)
    agent_handler.addFilter(LoggerFilter(
        prefixes=['agent.']
    ))
    root_logger.addHandler(agent_handler)

    # ===== 4. LargeRAG Handler =====
    largerag_file = log_dir / f"largerag_{timestamp}.log"
    largerag_handler = logging.handlers.RotatingFileHandler(
        largerag_file,
        maxBytes=100 * 1024 * 1024,
        backupCount=5,
        encoding='utf-8'
    )
    largerag_handler.setLevel(log_level)
    largerag_handler.setFormatter(formatter)
    largerag_handler.addFilter(LoggerFilter(
        prefixes=['largerag.']
    ))
    root_logger.addHandler(largerag_handler)

    # ===== 5. CoreRAG Handler =====
    corerag_file = log_dir / f"corerag_{timestamp}.log"
    corerag_handler = logging.handlers.RotatingFileHandler(
        corerag_file,
        maxBytes=100 * 1024 * 1024,
        backupCount=5,
        encoding='utf-8'
    )
    corerag_handler.setLevel(log_level)
    corerag_handler.setFormatter(formatter)
    corerag_handler.addFilter(LoggerFilter(
        prefixes=['autology_constructor.'],
        exact_names=['config.settings']  # CoreRAG settings module
    ))
    root_logger.addHandler(corerag_handler)

    # ===== 6. Root Handler (fallback for uncategorized logs) =====
    root_file = log_dir / f"root_{timestamp}.log"
    root_handler = logging.handlers.RotatingFileHandler(
        root_file,
        maxBytes=100 * 1024 * 1024,
        backupCount=5,
        encoding='utf-8'
    )
    root_handler.setLevel(log_level)
    root_handler.setFormatter(formatter)
    # Exclude logs that match other module filters
    root_handler.addFilter(ExcludeFilter(
        exclude_prefixes=['api.', 'services.', 'utils.', 'agent.', 'largerag.', 'autology_constructor.'],
        exclude_exact=['__main__', 'config', 'config.settings']
    ))
    root_logger.addHandler(root_handler)

    # Log configuration success
    logging.info(f"Logging configured: level={level}, log_dir={log_dir}")
    logging.info(f"Log files created with timestamp: {timestamp}")
    logging.info(f"  - {web_backend_file.name} (Web Backend)")
    logging.info(f"  - {agent_file.name} (Agent)")
    logging.info(f"  - {largerag_file.name} (LargeRAG)")
    logging.info(f"  - {corerag_file.name} (CoreRAG)")
    logging.info(f"  - {root_file.name} (Root)")


# For testing
if __name__ == "__main__":
    import tempfile

    # Test logging setup
    with tempfile.TemporaryDirectory() as tmpdir:
        setup_logging(Path(tmpdir), level="DEBUG")

        # Test different loggers
        logging.getLogger("api.tasks").info("Web backend log test")
        logging.getLogger("agent.des_agent").info("Agent log test")
        logging.getLogger("largerag.core.indexer").info("LargeRAG log test")
        logging.getLogger("autology_constructor.query_workflow").info("CoreRAG log test")
        logging.getLogger("some_third_party").info("Root log test")

        print(f"\nLog files created in: {tmpdir}")
        for f in Path(tmpdir).glob("*.log"):
            print(f"  - {f.name}")
