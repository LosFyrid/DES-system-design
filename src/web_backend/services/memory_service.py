"""
Memory Service

Business logic for managing ReasoningBank memories.
"""

import logging
from typing import List, Dict, Optional, Any
from datetime import datetime
from math import ceil

from models.schemas import (
    MemoryItemDetail,
    MemoryItemCreate,
    MemoryItemUpdate,
    MemoryListData
)
from utils.agent_loader import get_agent
from agent.reasoningbank.memory import MemoryItem

logger = logging.getLogger(__name__)


class MemoryService:
    """Service for managing memories in ReasoningBank"""

    def __init__(self):
        """Initialize memory service"""
        pass

    def list_memories(
        self,
        page: int = 1,
        page_size: int = 20,
        is_from_success: Optional[bool] = None,
        source_task_id: Optional[str] = None
    ) -> MemoryListData:
        """
        List memories with pagination and filtering.

        Args:
            page: Page number (1-indexed)
            page_size: Items per page
            is_from_success: Filter by success/failure
            source_task_id: Filter by source task

        Returns:
            MemoryListData with items and pagination
        """
        logger.info(f"Listing memories: page={page}, page_size={page_size}, is_from_success={is_from_success}")

        try:
            # Get agent's memory bank
            agent = get_agent()
            all_memories = agent.memory.get_all_memories()

            # Apply filters
            filtered_memories = all_memories
            if is_from_success is not None:
                filtered_memories = [m for m in filtered_memories if m.is_from_success == is_from_success]
            if source_task_id:
                filtered_memories = [m for m in filtered_memories if m.source_task_id == source_task_id]

            # Sort by created_at descending
            filtered_memories.sort(key=lambda m: m.created_at, reverse=True)

            # Pagination
            total = len(filtered_memories)
            total_pages = ceil(total / page_size) if total > 0 else 1
            start_idx = (page - 1) * page_size
            end_idx = start_idx + page_size
            page_memories = filtered_memories[start_idx:end_idx]

            # Convert to MemoryItemDetail
            items = [
                MemoryItemDetail(
                    title=m.title,
                    description=m.description,
                    content=m.content,
                    is_from_success=m.is_from_success,
                    source_task_id=m.source_task_id,
                    created_at=m.created_at,
                    metadata=m.metadata
                )
                for m in page_memories
            ]

            # Build filters info
            filters = {}
            if is_from_success is not None:
                filters["is_from_success"] = is_from_success
            if source_task_id:
                filters["source_task_id"] = source_task_id

            return MemoryListData(
                items=items,
                pagination={
                    "total": total,
                    "page": page,
                    "page_size": page_size,
                    "total_pages": total_pages
                },
                filters=filters
            )

        except Exception as e:
            logger.error(f"Failed to list memories: {e}", exc_info=True)
            raise RuntimeError(f"Failed to list memories: {str(e)}")

    def get_memory(self, title: str) -> MemoryItemDetail:
        """
        Get a memory by title.

        Args:
            title: Memory title

        Returns:
            MemoryItemDetail

        Raises:
            ValueError: If memory not found
            RuntimeError: If retrieval fails
        """
        logger.info(f"Getting memory: {title}")

        try:
            # Get agent's memory bank
            agent = get_agent()
            memory = agent.memory.get_memory_by_title(title)

            if not memory:
                raise ValueError(f"Memory with title '{title}' not found")

            return MemoryItemDetail(
                title=memory.title,
                description=memory.description,
                content=memory.content,
                is_from_success=memory.is_from_success,
                source_task_id=memory.source_task_id,
                created_at=memory.created_at,
                metadata=memory.metadata
            )

        except ValueError as e:
            # Re-raise ValueError
            raise
        except Exception as e:
            logger.error(f"Failed to get memory: {e}", exc_info=True)
            raise RuntimeError(f"Failed to get memory: {str(e)}")

    def create_memory(self, memory_data: MemoryItemCreate) -> MemoryItemDetail:
        """
        Create a new memory.

        Args:
            memory_data: Memory creation data

        Returns:
            MemoryItemDetail

        Raises:
            ValueError: If title already exists
            RuntimeError: If creation fails
        """
        logger.info(f"Creating memory: {memory_data.title}")

        try:
            # Get agent's memory bank
            agent = get_agent()

            # Check if title already exists
            existing = agent.memory.get_memory_by_title(memory_data.title)
            if existing:
                raise ValueError(f"Memory with title '{memory_data.title}' already exists")

            # Create MemoryItem
            new_memory = MemoryItem(
                title=memory_data.title,
                description=memory_data.description,
                content=memory_data.content,
                source_task_id=memory_data.source_task_id,
                is_from_success=memory_data.is_from_success,
                created_at=datetime.now().isoformat(),
                embedding=None,  # Will be computed by add_memory if embedding_func is set
                metadata=memory_data.metadata or {}
            )

            # Add to memory bank
            agent.memory.add_memory(new_memory, compute_embedding=True)

            # Save if auto_save is enabled
            if agent.config.get("memory", {}).get("auto_save", False):
                save_path = agent.config["memory"]["persist_path"]
                agent.memory.save(save_path)
                logger.info(f"Auto-saved memory bank to {save_path}")

            return MemoryItemDetail(
                title=new_memory.title,
                description=new_memory.description,
                content=new_memory.content,
                is_from_success=new_memory.is_from_success,
                source_task_id=new_memory.source_task_id,
                created_at=new_memory.created_at,
                metadata=new_memory.metadata
            )

        except ValueError as e:
            # Re-raise ValueError
            raise
        except Exception as e:
            logger.error(f"Failed to create memory: {e}", exc_info=True)
            raise RuntimeError(f"Failed to create memory: {str(e)}")

    def update_memory(self, title: str, update_data: MemoryItemUpdate) -> MemoryItemDetail:
        """
        Update an existing memory.

        Args:
            title: Memory title
            update_data: Update data

        Returns:
            MemoryItemDetail

        Raises:
            ValueError: If memory not found
            RuntimeError: If update fails
        """
        logger.info(f"Updating memory: {title}")

        try:
            # Get agent's memory bank
            agent = get_agent()

            # Get existing memory
            memory = agent.memory.get_memory_by_title(title)
            if not memory:
                raise ValueError(f"Memory with title '{title}' not found")

            # Update fields
            if update_data.description is not None:
                memory.description = update_data.description
            if update_data.content is not None:
                memory.content = update_data.content
            if update_data.is_from_success is not None:
                memory.is_from_success = update_data.is_from_success
            if update_data.metadata is not None:
                # Merge metadata
                memory.metadata.update(update_data.metadata)

            # If content changed, recompute embedding
            if update_data.description is not None or update_data.content is not None:
                if agent.memory.embedding_func:
                    try:
                        embed_text = f"{memory.title}. {memory.description}"
                        memory.embedding = agent.memory.embedding_func(embed_text)
                        logger.debug(f"Recomputed embedding for updated memory: {memory.title}")
                    except Exception as e:
                        logger.warning(f"Failed to recompute embedding: {e}")

            # Save if auto_save is enabled
            if agent.config.get("memory", {}).get("auto_save", False):
                save_path = agent.config["memory"]["persist_path"]
                agent.memory.save(save_path)
                logger.info(f"Auto-saved memory bank to {save_path}")

            return MemoryItemDetail(
                title=memory.title,
                description=memory.description,
                content=memory.content,
                is_from_success=memory.is_from_success,
                source_task_id=memory.source_task_id,
                created_at=memory.created_at,
                metadata=memory.metadata
            )

        except ValueError as e:
            # Re-raise ValueError
            raise
        except Exception as e:
            logger.error(f"Failed to update memory: {e}", exc_info=True)
            raise RuntimeError(f"Failed to update memory: {str(e)}")

    def delete_memory(self, title: str) -> Dict[str, str]:
        """
        Delete a memory.

        Args:
            title: Memory title

        Returns:
            Dict with deletion confirmation

        Raises:
            ValueError: If memory not found
            RuntimeError: If deletion fails
        """
        logger.info(f"Deleting memory: {title}")

        try:
            # Get agent's memory bank
            agent = get_agent()

            # Check if exists
            memory = agent.memory.get_memory_by_title(title)
            if not memory:
                raise ValueError(f"Memory with title '{title}' not found")

            # Delete from memory bank
            deleted = agent.memory.delete_by_title(title)

            if not deleted:
                raise RuntimeError(f"Failed to delete memory '{title}'")

            # Save if auto_save is enabled
            if agent.config.get("memory", {}).get("auto_save", False):
                save_path = agent.config["memory"]["persist_path"]
                agent.memory.save(save_path)
                logger.info(f"Auto-saved memory bank to {save_path}")

            return {
                "title": title,
                "deleted_at": datetime.now().isoformat()
            }

        except ValueError as e:
            # Re-raise ValueError
            raise
        except Exception as e:
            logger.error(f"Failed to delete memory: {e}", exc_info=True)
            raise RuntimeError(f"Failed to delete memory: {str(e)}")


# Singleton instance
_service: MemoryService = None


def get_memory_service() -> MemoryService:
    """Get memory service singleton"""
    global _service
    if _service is None:
        _service = MemoryService()
    return _service
