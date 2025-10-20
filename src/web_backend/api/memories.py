"""
Memory Management API endpoints

Handles CRUD operations for ReasoningBank memories.
"""

import logging
from fastapi import APIRouter, HTTPException, Query, status

from models.schemas import (
    MemoryListResponse,
    MemoryDetailResponse,
    MemoryCreateResponse,
    MemoryUpdateResponse,
    MemoryDeleteResponse,
    MemoryItemCreate,
    MemoryItemUpdate,
    ErrorResponse
)
from services.memory_service import get_memory_service
from utils.response import error_response

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get(
    "/",
    response_model=MemoryListResponse,
    status_code=status.HTTP_200_OK,
    summary="List all memories",
    description="Get a paginated list of memories with optional filtering",
    responses={
        200: {"description": "Memories retrieved successfully", "model": MemoryListResponse},
        500: {"description": "Internal server error", "model": ErrorResponse}
    }
)
async def list_memories(
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    is_from_success: bool = Query(None, description="Filter by success/failure origin"),
    source_task_id: str = Query(None, description="Filter by source task/recommendation ID")
):
    """
    List all memories with pagination and optional filtering.

    **Query Parameters**:
    - **page**: Page number (1-indexed, default: 1)
    - **page_size**: Items per page (1-100, default: 20)
    - **is_from_success**: Filter by whether memory is from successful experiment (optional)
    - **source_task_id**: Filter by source task or recommendation ID (optional)

    **Example Request**:
    ```
    GET /api/v1/memories?page=1&page_size=20&is_from_success=true
    ```

    **Example Response**:
    ```json
    {
      "status": "success",
      "message": "Retrieved 15 memories (page 1/3)",
      "data": {
        "items": [
          {
            "title": "Prioritize H-Bond Analysis",
            "description": "Analyze hydrogen bonding first for polar materials",
            "content": "For dissolving polar polymers, H-bond strength is the primary factor...",
            "is_from_success": true,
            "source_task_id": "REC_20251020_001",
            "created_at": "2025-10-20T10:30:00",
            "metadata": {"solubility": 6.5, "solubility_unit": "g/L"}
          }
        ],
        "pagination": {
          "total": 50,
          "page": 1,
          "page_size": 20,
          "total_pages": 3
        },
        "filters": {
          "is_from_success": true
        }
      }
    }
    ```
    """
    try:
        memory_service = get_memory_service()
        memory_data = memory_service.list_memories(
            page=page,
            page_size=page_size,
            is_from_success=is_from_success,
            source_task_id=source_task_id
        )

        return MemoryListResponse(
            status="success",
            message=(
                f"Retrieved {len(memory_data.items)} memories "
                f"(page {memory_data.pagination['page']}/{memory_data.pagination['total_pages']})"
            ),
            data=memory_data
        )

    except Exception as e:
        logger.error(f"Failed to list memories: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_response(message=f"Failed to list memories: {str(e)}")
        )


@router.get(
    "/{title}",
    response_model=MemoryDetailResponse,
    status_code=status.HTTP_200_OK,
    summary="Get memory by title",
    description="Get detailed information about a specific memory",
    responses={
        200: {"description": "Memory retrieved successfully", "model": MemoryDetailResponse},
        404: {"description": "Memory not found", "model": ErrorResponse},
        500: {"description": "Internal server error", "model": ErrorResponse}
    }
)
async def get_memory(title: str):
    """
    Get a memory by its title.

    **Path Parameters**:
    - **title**: Memory title (exact match)

    **Example Response**:
    ```json
    {
      "status": "success",
      "message": "Memory retrieved successfully",
      "data": {
        "title": "Prioritize H-Bond Analysis",
        "description": "Analyze hydrogen bonding first for polar materials",
        "content": "For dissolving polar polymers like cellulose, the hydrogen bond donating/accepting capability of DES components is the primary factor. Use CoreRAG to retrieve H-bond parameters before exploring molar ratios.",
        "is_from_success": true,
        "source_task_id": "REC_20251020_001",
        "created_at": "2025-10-20T10:30:00",
        "metadata": {
          "solubility": 6.5,
          "solubility_unit": "g/L",
          "source": "experiment_validated"
        }
      }
    }
    ```
    """
    try:
        memory_service = get_memory_service()
        memory = memory_service.get_memory(title)

        return MemoryDetailResponse(
            status="success",
            message="Memory retrieved successfully",
            data=memory
        )

    except ValueError as e:
        # Memory not found
        logger.warning(f"Memory not found: {title}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=error_response(message=str(e))
        )

    except Exception as e:
        logger.error(f"Failed to get memory: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_response(message=f"Failed to get memory: {str(e)}")
        )


@router.post(
    "/",
    response_model=MemoryCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new memory",
    description="Create a new memory item in ReasoningBank",
    responses={
        201: {"description": "Memory created successfully", "model": MemoryCreateResponse},
        400: {"description": "Validation error or title already exists", "model": ErrorResponse},
        500: {"description": "Internal server error", "model": ErrorResponse}
    }
)
async def create_memory(memory_data: MemoryItemCreate):
    """
    Create a new memory item.

    **Request Body**:
    ```json
    {
      "title": "Avoid High Viscosity Combinations",
      "description": "Some HBD-HBA pairs result in very high viscosity",
      "content": "Glycerol-based DES tend to have high viscosity at room temperature, which can hinder mass transfer. Consider using shorter-chain polyols for better fluidity.",
      "is_from_success": false,
      "source_task_id": "REC_20251020_005",
      "metadata": {
        "viscosity": 450,
        "temperature": 25
      }
    }
    ```

    **Validation Rules**:
    - Title must be unique (1-200 characters)
    - Description required (1-500 characters)
    - Content required (1-2000 characters)
    - Title cannot match existing memory

    **Notes**:
    - Embedding will be automatically computed if embedding function is configured
    - Memory will be auto-saved if auto_save is enabled in config
    """
    try:
        memory_service = get_memory_service()
        created_memory = memory_service.create_memory(memory_data)

        return MemoryCreateResponse(
            status="success",
            message=f"Memory '{created_memory.title}' created successfully",
            data=created_memory
        )

    except ValueError as e:
        # Title already exists or validation error
        logger.warning(f"Failed to create memory: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_response(message=str(e))
        )

    except Exception as e:
        logger.error(f"Failed to create memory: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_response(message=f"Failed to create memory: {str(e)}")
        )


@router.put(
    "/{title}",
    response_model=MemoryUpdateResponse,
    status_code=status.HTTP_200_OK,
    summary="Update a memory",
    description="Update an existing memory item",
    responses={
        200: {"description": "Memory updated successfully", "model": MemoryUpdateResponse},
        404: {"description": "Memory not found", "model": ErrorResponse},
        500: {"description": "Internal server error", "model": ErrorResponse}
    }
)
async def update_memory(title: str, update_data: MemoryItemUpdate):
    """
    Update an existing memory.

    **Path Parameters**:
    - **title**: Memory title (exact match)

    **Request Body** (all fields optional):
    ```json
    {
      "description": "Updated description",
      "content": "Updated content with more details...",
      "is_from_success": true,
      "metadata": {
        "updated_reason": "Added more context"
      }
    }
    ```

    **Notes**:
    - Only provided fields will be updated
    - Title cannot be changed (use delete + create to rename)
    - Metadata will be merged with existing metadata
    - Embedding will be recomputed if description or content changes
    - Auto-saved if auto_save is enabled
    """
    try:
        memory_service = get_memory_service()
        updated_memory = memory_service.update_memory(title, update_data)

        return MemoryUpdateResponse(
            status="success",
            message=f"Memory '{updated_memory.title}' updated successfully",
            data=updated_memory
        )

    except ValueError as e:
        # Memory not found
        logger.warning(f"Failed to update memory: {e}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=error_response(message=str(e))
        )

    except Exception as e:
        logger.error(f"Failed to update memory: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_response(message=f"Failed to update memory: {str(e)}")
        )


@router.delete(
    "/{title}",
    response_model=MemoryDeleteResponse,
    status_code=status.HTTP_200_OK,
    summary="Delete a memory",
    description="Delete a memory from ReasoningBank",
    responses={
        200: {"description": "Memory deleted successfully", "model": MemoryDeleteResponse},
        404: {"description": "Memory not found", "model": ErrorResponse},
        500: {"description": "Internal server error", "model": ErrorResponse}
    }
)
async def delete_memory(title: str):
    """
    Delete a memory by its title.

    **Path Parameters**:
    - **title**: Memory title (exact match)

    **Example Response**:
    ```json
    {
      "status": "success",
      "message": "Memory 'Avoid High Viscosity Combinations' deleted successfully",
      "data": {
        "title": "Avoid High Viscosity Combinations",
        "deleted_at": "2025-10-20T15:30:00"
      }
    }
    ```

    **Warning**:
    - This operation cannot be undone
    - Memory bank will be auto-saved if auto_save is enabled
    """
    try:
        memory_service = get_memory_service()
        result = memory_service.delete_memory(title)

        return MemoryDeleteResponse(
            status="success",
            message=f"Memory '{title}' deleted successfully",
            data=result
        )

    except ValueError as e:
        # Memory not found
        logger.warning(f"Failed to delete memory: {e}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=error_response(message=str(e))
        )

    except Exception as e:
        logger.error(f"Failed to delete memory: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_response(message=f"Failed to delete memory: {str(e)}")
        )
