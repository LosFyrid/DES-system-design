"""
Pydantic models for API request/response validation

These models define the data structures for all API endpoints,
ensuring type safety and automatic validation.
"""

from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field, field_validator
from datetime import datetime


# ===== Base Response Models =====

class BaseResponse(BaseModel):
    """Base response model for all API responses"""
    status: str = Field(..., description="Response status: success or error")
    message: Optional[str] = Field(None, description="Human-readable message")


class ErrorDetail(BaseModel):
    """Error detail for validation errors"""
    field: str = Field(..., description="Field name with error")
    message: str = Field(..., description="Error message")


class ErrorResponse(BaseResponse):
    """Error response model"""
    status: str = Field(default="error")
    errors: Optional[List[ErrorDetail]] = Field(None, description="List of errors")


# ===== Task Management Models =====

class TaskRequest(BaseModel):
    """Request model for creating a DES formulation task"""
    description: str = Field(
        ...,
        min_length=10,
        max_length=1000,
        description="Natural language description of the task",
        json_schema_extra={"example": "Design a DES formulation to dissolve cellulose at room temperature (25°C)"}
    )
    target_material: str = Field(
        ...,
        min_length=2,
        max_length=100,
        description="Material to dissolve (e.g., cellulose, lignin, chitin)",
        json_schema_extra={"example": "cellulose"}
    )
    target_temperature: Optional[float] = Field(
        default=25.0,
        ge=-50,
        le=200,
        description="Target temperature in Celsius",
        json_schema_extra={"example": 25.0}
    )
    num_components: Optional[int] = Field(
        default=2,
        ge=2,
        le=10,
        description="Number of DES components (2=binary, 3=ternary, 4=quaternary, 5+=multi-component)",
        json_schema_extra={"example": 2}
    )
    constraints: Optional[Dict[str, str]] = Field(
        default_factory=dict,
        description="Additional constraints (key-value pairs)",
        json_schema_extra={"example": {"max_viscosity": "500 cP", "component_availability": "common chemicals only"}}
    )
    task_id: Optional[str] = Field(
        None,
        description="Optional task ID (auto-generated if not provided)",
        json_schema_extra={"example": "task_001"}
    )

    @field_validator('target_material')
    @classmethod
    def validate_material(cls, v: str) -> str:
        """Validate and normalize material name"""
        return v.strip().lower()


class ComponentData(BaseModel):
    """Single component in a DES formulation"""
    name: str = Field(..., description="Component name")
    role: str = Field(..., description="Component role (HBD, HBA, modifier, etc.)")
    function: Optional[str] = Field(None, description="Component function/purpose")


class FormulationData(BaseModel):
    """DES formulation data - supports both binary and multi-component formulations"""
    # Binary formulation fields (backward compatible)
    HBD: Optional[str] = Field(None, description="Hydrogen Bond Donor (for binary DES)", json_schema_extra={"example": "Urea"})
    HBA: Optional[str] = Field(None, description="Hydrogen Bond Acceptor (for binary DES)", json_schema_extra={"example": "Choline chloride"})

    # Multi-component formulation fields
    components: Optional[List[ComponentData]] = Field(None, description="List of components (for multi-component DES)")
    num_components: Optional[int] = Field(None, description="Number of components")

    # Common fields
    molar_ratio: str = Field(..., description="Molar ratio", json_schema_extra={"example": "1:2"})

    def is_binary(self) -> bool:
        """Check if this is a binary formulation"""
        return self.HBD is not None and self.HBA is not None

    def is_multi_component(self) -> bool:
        """Check if this is a multi-component formulation"""
        return self.components is not None and len(self.components) > 2

    def get_display_string(self) -> str:
        """Get human-readable formulation string"""
        if self.is_binary():
            return f"{self.HBD} : {self.HBA} ({self.molar_ratio})"
        elif self.is_multi_component():
            component_names = " + ".join([c.name for c in self.components])
            return f"{component_names} ({self.molar_ratio})"
        else:
            return f"Unknown formulation ({self.molar_ratio})"


class TaskData(BaseModel):
    """Task data in response"""
    task_id: str
    recommendation_id: str
    formulation: FormulationData
    reasoning: str = Field(..., description="Explanation of design choices")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score (0-1)")
    supporting_evidence: List[str] = Field(default_factory=list, description="Supporting facts from memory/theory/literature")
    status: str = Field(..., description="Status: PENDING, COMPLETED, CANCELLED")
    created_at: str = Field(..., description="Creation timestamp (ISO format)")
    memories_used: Optional[List[str]] = Field(default_factory=list, description="Titles of retrieved memories")
    next_steps: Optional[str] = Field(None, description="Next steps for the user")


class TaskResponse(BaseResponse):
    """Response model for task creation"""
    status: str = Field(default="success")
    data: TaskData


# ===== Recommendation Management Models =====

class RecommendationSummary(BaseModel):
    """Summary of a recommendation (for list view)"""
    recommendation_id: str
    task_id: str
    target_material: str
    target_temperature: float
    formulation: FormulationData
    confidence: float = Field(..., ge=0.0, le=1.0)
    status: str = Field(..., description="PENDING, COMPLETED, CANCELLED")
    created_at: str
    updated_at: str
    performance_score: Optional[float] = Field(None, ge=0.0, le=10.0, description="Performance score from experiment (0-10)")


class RecommendationListData(BaseModel):
    """Data for recommendation list response"""
    items: List[RecommendationSummary]
    pagination: Dict[str, int] = Field(
        ...,
        description="Pagination info",
        json_schema_extra={"example": {"total": 45, "page": 1, "page_size": 20, "total_pages": 3}}
    )


class RecommendationListResponse(BaseResponse):
    """Response model for recommendation list"""
    status: str = Field(default="success")
    data: RecommendationListData


class TrajectoryStep(BaseModel):
    """Single step in trajectory"""
    action: str
    reasoning: str
    tool: Optional[str] = None
    num_memories: Optional[int] = None
    formulation: Optional[FormulationData] = None


class Trajectory(BaseModel):
    """Complete trajectory of recommendation generation"""
    steps: List[TrajectoryStep]
    tool_calls: List[Dict[str, Any]] = Field(default_factory=list)


class ExperimentResultData(BaseModel):
    """Experimental result data"""
    is_liquid_formed: bool = Field(..., description="Whether DES formed liquid phase")
    solubility: Optional[float] = Field(None, description="Solubility of target material")
    solubility_unit: str = Field(default="g/L", description="Unit of solubility")
    properties: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional properties (e.g., viscosity, density)",
        json_schema_extra={"example": {"viscosity": "45 cP", "appearance": "clear liquid"}}
    )
    experimenter: Optional[str] = Field(None, description="Name of experimenter")
    experiment_date: str = Field(..., description="Experiment date (ISO format)")
    notes: str = Field(default="", description="Experimental notes")
    performance_score: float = Field(..., ge=0.0, le=10.0, description="Performance score (0-10)")


class MemoryItemSummary(BaseModel):
    """Summary of a memory item used in recommendation"""
    title: str = Field(..., description="Memory title")
    description: str = Field(..., description="One-sentence description")
    content: str = Field(..., description="Detailed content")
    is_from_success: bool = Field(..., description="Whether from successful experiment")


class RecommendationDetail(BaseModel):
    """Detailed recommendation data"""
    recommendation_id: str
    task: Dict[str, Any] = Field(..., description="Original task specification")
    formulation: FormulationData
    reasoning: str
    confidence: float = Field(..., ge=0.0, le=1.0)
    supporting_evidence: List[str]
    memories_used: Optional[List[MemoryItemSummary]] = Field(default_factory=list, description="Memories retrieved and used for this recommendation")
    status: str
    trajectory: Trajectory
    experiment_result: Optional[ExperimentResultData] = None
    created_at: str
    updated_at: str


class RecommendationDetailResponse(BaseResponse):
    """Response model for recommendation detail"""
    status: str = Field(default="success")
    data: RecommendationDetail


# ===== Feedback Management Models =====

class ExperimentResultRequest(BaseModel):
    """Request model for submitting experimental feedback"""
    is_liquid_formed: bool = Field(
        ...,
        description="Whether the DES formed a liquid phase",
        json_schema_extra={"example": True}
    )
    solubility: Optional[float] = Field(
        None,
        ge=0.0,
        description="Solubility of target material (required if is_liquid_formed=True)",
        json_schema_extra={"example": 6.5}
    )
    solubility_unit: str = Field(
        default="g/L",
        description="Unit of solubility measurement",
        json_schema_extra={"example": "g/L"}
    )
    properties: Optional[Dict[str, str]] = Field(
        default_factory=dict,
        description="Additional measured properties (key-value pairs)",
        json_schema_extra={"example": {"viscosity": "45 cP", "density": "1.15 g/mL"}}
    )
    experimenter: Optional[str] = Field(
        None,
        description="Name of person who performed the experiment",
        json_schema_extra={"example": "Dr. Zhang"}
    )
    notes: str = Field(
        default="",
        max_length=2000,
        description="Experimental notes and observations",
        json_schema_extra={"example": "DES formed successfully at room temperature. Clear liquid observed."}
    )

    @field_validator('solubility')
    @classmethod
    def validate_solubility(cls, v: Optional[float], info) -> Optional[float]:
        """Validate solubility based on is_liquid_formed"""
        # Note: In Pydantic v2, we can't access other fields in validator directly
        # This validation will be done in the service layer
        return v


class FeedbackRequest(BaseModel):
    """Request model for feedback submission"""
    recommendation_id: str = Field(
        ...,
        description="ID of the recommendation to update",
        json_schema_extra={"example": "REC_20251016_123456_task_001"}
    )
    experiment_result: ExperimentResultRequest


class FeedbackData(BaseModel):
    """Feedback processing result data"""
    recommendation_id: str
    # Use raw solubility instead of performance_score
    solubility: Optional[float] = Field(None, description="Measured solubility")
    solubility_unit: str = Field(default="g/L", description="Unit of solubility")
    is_liquid_formed: Optional[bool] = Field(None, description="Whether DES liquid formed")
    memories_extracted: List[str] = Field(..., description="Titles of extracted memories")
    num_memories: int = Field(..., description="Number of memories extracted")
    # Deprecated: kept for backward compatibility
    performance_score: Optional[float] = Field(None, ge=0.0, le=10.0, deprecated=True, description="[DEPRECATED] Use solubility instead")


class FeedbackResponse(BaseResponse):
    """Response model for feedback submission"""
    status: str = Field(default="success")
    data: FeedbackData


class FeedbackAsyncResponse(BaseResponse):
    """Response model for async feedback submission"""
    status: str = Field(default="accepted")
    recommendation_id: str = Field(..., description="Recommendation ID")
    processing: str = Field(default="started", description="Processing status")


class FeedbackStatusData(BaseModel):
    """Feedback processing status data"""
    status: str = Field(..., description="processing|completed|failed")
    started_at: str = Field(..., description="Processing start time")
    completed_at: Optional[str] = Field(None, description="Processing completion time")
    failed_at: Optional[str] = Field(None, description="Processing failure time")
    result: Optional[FeedbackData] = Field(None, description="Processing result (if completed)")
    error: Optional[str] = Field(None, description="Error message (if failed)")
    is_update: Optional[bool] = Field(None, description="Whether this is an update operation")
    deleted_memories: Optional[int] = Field(None, description="Number of deleted memories (if update)")


class FeedbackStatusResponse(BaseResponse):
    """Response model for feedback processing status"""
    status: str = Field(default="success")
    data: FeedbackStatusData


# ===== Statistics Models =====

class SummaryStatistics(BaseModel):
    """Summary statistics"""
    total_recommendations: int
    pending_experiments: int
    completed_experiments: int
    cancelled: int
    average_performance_score: float = Field(..., ge=0.0, le=10.0)
    liquid_formation_rate: float = Field(..., ge=0.0, le=1.0, description="Rate of successful liquid formation")


class PerformanceTrendPoint(BaseModel):
    """Single point in performance trend"""
    date: str = Field(..., description="Date (YYYY-MM-DD)")
    avg_solubility: float = Field(..., ge=0.0)
    solubility_unit: str = Field(default="g/L", description="Unit for solubility (common unit if mixed)")
    avg_performance_score: float = Field(..., ge=0.0, le=10.0)
    experiment_count: int = Field(..., ge=0)
    liquid_formation_rate: float = Field(..., ge=0.0, le=1.0)


class TopFormulation(BaseModel):
    """Top performing formulation"""
    formulation: str = Field(..., description="Formulation string (e.g., 'ChCl:Urea (1:2)')")
    avg_performance: float = Field(..., ge=0.0, le=10.0, description="Average solubility (note: field name kept for API compatibility)")
    solubility_unit: str = Field(default="g/L", description="Unit for avg_performance (solubility)")
    success_count: int = Field(..., ge=0)


class StatisticsData(BaseModel):
    """Statistics data"""
    summary: SummaryStatistics
    by_material: Dict[str, int] = Field(..., description="Count by material")
    by_status: Dict[str, int] = Field(..., description="Count by status")
    performance_trend: List[PerformanceTrendPoint]
    top_formulations: List[TopFormulation]


class StatisticsResponse(BaseResponse):
    """Response model for statistics"""
    status: str = Field(default="success")
    data: StatisticsData


class PerformanceTrendResponse(BaseResponse):
    """Response model for performance trend"""
    status: str = Field(default="success")
    data: List[PerformanceTrendPoint]


# ===== Admin Models =====

class LoadHistoricalDataRequest(BaseModel):
    """Request model for loading historical data"""
    data_path: str = Field(
        ...,
        description="Path to directory containing recommendation JSON files",
        json_schema_extra={"example": "/path/to/system_A/recommendations/"}
    )
    reprocess: bool = Field(
        default=True,
        description="Whether to reprocess with current extraction logic"
    )


class LoadHistoricalDataResult(BaseModel):
    """Result of historical data loading"""
    num_loaded: int
    num_reprocessed: int
    memories_added: int


class LoadHistoricalDataResponse(BaseResponse):
    """Response model for historical data loading"""
    status: str = Field(default="success")
    data: LoadHistoricalDataResult


# ===== Memory Management Models =====

class MemoryItemDetail(BaseModel):
    """Detailed memory item for management"""
    title: str = Field(..., min_length=1, max_length=200, description="Memory title")
    description: str = Field(..., min_length=1, max_length=500, description="One-sentence description")
    content: str = Field(..., min_length=1, max_length=2000, description="Detailed content (1-5 sentences)")
    is_from_success: bool = Field(default=True, description="Whether from successful experiment")
    source_task_id: Optional[str] = Field(None, description="Source task/recommendation ID")
    created_at: str = Field(..., description="Creation timestamp")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")


class MemoryItemCreate(BaseModel):
    """Request model for creating a memory"""
    title: str = Field(..., min_length=1, max_length=200, description="Memory title (must be unique)")
    description: str = Field(..., min_length=1, max_length=500, description="One-sentence description")
    content: str = Field(..., min_length=1, max_length=2000, description="Detailed content")
    is_from_success: bool = Field(default=True, description="Whether from successful experiment")
    source_task_id: Optional[str] = Field(None, description="Source task/recommendation ID")
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Additional metadata")


class MemoryItemUpdate(BaseModel):
    """Request model for updating a memory"""
    description: Optional[str] = Field(None, min_length=1, max_length=500, description="One-sentence description")
    content: Optional[str] = Field(None, min_length=1, max_length=2000, description="Detailed content")
    is_from_success: Optional[bool] = Field(None, description="Whether from successful experiment")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional metadata to merge")


class MemoryListData(BaseModel):
    """Data for memory list response"""
    items: List[MemoryItemDetail]
    pagination: Dict[str, int] = Field(
        ...,
        description="Pagination info",
        json_schema_extra={"example": {"total": 50, "page": 1, "page_size": 20, "total_pages": 3}}
    )
    filters: Dict[str, Any] = Field(
        default_factory=dict,
        description="Applied filters"
    )


class MemoryListResponse(BaseResponse):
    """Response model for memory list"""
    status: str = Field(default="success")
    data: MemoryListData


class MemoryDetailResponse(BaseResponse):
    """Response model for single memory detail"""
    status: str = Field(default="success")
    data: MemoryItemDetail


class MemoryCreateResponse(BaseResponse):
    """Response model for memory creation"""
    status: str = Field(default="success")
    data: MemoryItemDetail
    message: str = Field(default="Memory created successfully")


class MemoryUpdateResponse(BaseResponse):
    """Response model for memory update"""
    status: str = Field(default="success")
    data: MemoryItemDetail
    message: str = Field(default="Memory updated successfully")


class MemoryDeleteResponse(BaseResponse):
    """Response model for memory deletion"""
    status: str = Field(default="success")
    data: Dict[str, str] = Field(..., description="Deletion confirmation")
    message: str = Field(default="Memory deleted successfully")
