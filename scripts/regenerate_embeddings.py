"""
Regenerate embeddings for existing memories in reasoning_bank.json

This script fixes the issue where memories were saved without embeddings,
causing retrieval to fail (retriever skips memories with None embedding).
"""

import sys
import json
import logging
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

# Load .env file for API keys
from dotenv import load_dotenv
load_dotenv(project_root / ".env")

from agent.reasoningbank import ReasoningBank, MemoryItem
from agent.utils.embedding_client import EmbeddingClient
from agent.config import get_config

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    """Regenerate embeddings for all memories"""

    # Load configuration
    config = get_config()
    embedding_config = config.get_embedding_config()

    # Initialize embedding client
    logger.info(f"Initializing embedding client: {embedding_config['provider']}/{embedding_config['model']}")
    embedding_client = EmbeddingClient(
        provider=embedding_config["provider"],
        model=embedding_config["model"],
        base_url=embedding_config.get("api_base")
    )

    # Path to memory file
    memory_file = project_root / "data" / "memory" / "reasoning_bank.json"

    if not memory_file.exists():
        logger.error(f"Memory file not found: {memory_file}")
        return 1

    logger.info(f"Loading memory file: {memory_file}")

    # Load existing memories
    with open(memory_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    memories_data = data.get("memories", [])
    logger.info(f"Found {len(memories_data)} memories")

    # Count memories without embeddings
    no_embedding_count = sum(1 for m in memories_data if m.get("embedding") is None)
    logger.info(f"Memories without embeddings: {no_embedding_count}")

    if no_embedding_count == 0:
        logger.info("All memories already have embeddings. Nothing to do.")
        return 0

    # Initialize ReasoningBank with embedding function
    bank = ReasoningBank(
        embedding_func=embedding_client.embed,
        max_items=data.get("max_items", 1000)
    )

    # Convert to MemoryItem objects and regenerate embeddings
    updated_count = 0
    for mem_data in memories_data:
        memory = MemoryItem.from_dict(mem_data)

        if memory.embedding is None:
            # Generate embedding
            embed_text = f"{memory.title}. {memory.description}"
            try:
                memory.embedding = embedding_client.embed(embed_text)
                updated_count += 1
                logger.info(f"Generated embedding for: {memory.title[:50]}...")
            except Exception as e:
                logger.error(f"Failed to generate embedding for '{memory.title}': {e}")

        # Add to bank (will use existing embedding if already present)
        bank.add_memory(memory, compute_embedding=False)

    # Save updated bank
    backup_file = memory_file.with_suffix(".json.backup")
    logger.info(f"Creating backup: {backup_file}")
    memory_file.rename(backup_file)

    bank.save(str(memory_file))
    logger.info(f"Saved updated memory bank: {memory_file}")
    logger.info(f"✅ Successfully regenerated {updated_count} embeddings")

    return 0


if __name__ == "__main__":
    sys.exit(main())
