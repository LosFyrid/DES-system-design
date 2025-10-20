/**
 * TypeScript type definitions for DES Formulation System
 * Corresponds to backend Pydantic models in src/web_backend/models/schemas.py
 */

// ============================================
// Task Related Types
// ============================================

export interface TaskRequest {
  description: string;
  target_material: string;
  target_temperature?: number;
  num_components?: number;
  constraints?: Record<string, string>;
}

export interface ComponentData {
  name: string;
  role: string;
  function?: string;
}

export interface FormulationData {
  // Binary formulation fields (backward compatible)
  HBD?: string;
  HBA?: string;

  // Multi-component formulation fields
  components?: ComponentData[];
  num_components?: number;

  // Common fields
  molar_ratio: string;
}

export interface RecommendationSummary {
  recommendation_id: string;
  task_id: string;
  target_material: string;
  target_temperature: number;
  formulation: FormulationData;
  confidence: number;
  status: 'GENERATING' | 'PENDING' | 'PROCESSING' | 'COMPLETED' | 'CANCELLED' | 'FAILED';
  created_at: string;
  updated_at: string;
  performance_score?: number;
}

export interface TaskData {
  task_id: string;
  description: string;
  target_material: string;
  target_temperature: number;
  num_components?: number;
  constraints: Record<string, string>;
  recommendations: RecommendationSummary[];
  created_at: string;
}

export interface TaskResponse {
  status: string;
  message: string;
  data: TaskData;
}

// ============================================
// Recommendation Related Types
// ============================================

export interface MemoryItemSummary {
  title: string;
  description: string;
  content: string;
  is_from_success: boolean;
}

export interface TrajectoryStep {
  action: string;
  reasoning: string;
  tool?: string;
  num_memories?: number;
  formulation?: FormulationData;
}

export interface Trajectory {
  steps: TrajectoryStep[];
  tool_calls: any[];
}

export interface ExperimentResult {
  is_liquid_formed: boolean;
  solubility?: number;
  solubility_unit: string;
  properties: Record<string, any>;
  experimenter?: string;
  experiment_date: string;
  notes: string;
  performance_score: number;
}

export interface RecommendationDetail {
  recommendation_id: string;
  task: Record<string, any>;
  formulation: FormulationData;
  reasoning: string;
  confidence: number;
  supporting_evidence: string[];
  memories_used?: MemoryItemSummary[];
  status: 'GENERATING' | 'PENDING' | 'PROCESSING' | 'COMPLETED' | 'CANCELLED' | 'FAILED';
  trajectory: Trajectory;
  experiment_result?: ExperimentResult;
  created_at: string;
  updated_at: string;
}

export interface RecommendationListData {
  items: RecommendationSummary[];
  pagination: {
    total: number;
    page: number;
    page_size: number;
    total_pages: number;
  };
}

export interface RecommendationListResponse {
  status: string;
  message: string;
  data: RecommendationListData;
}

export interface RecommendationDetailResponse {
  status: string;
  message: string;
  data: RecommendationDetail;
}

export interface CancelRecommendationResponse {
  status: string;
  message: string;
  data: {
    recommendation_id: string;
    status: string;
    cancelled_at: string;
  };
}

// ============================================
// Feedback Related Types
// ============================================

export interface ExperimentResultRequest {
  is_liquid_formed: boolean;
  solubility?: number;
  solubility_unit?: string;
  temperature?: number;
  properties?: Record<string, string>;
  notes?: string;
}

export interface FeedbackRequest {
  recommendation_id: string;
  experiment_result: ExperimentResultRequest;
}

export interface FeedbackData {
  recommendation_id: string;
  status: string;
  experiment_result: ExperimentResult;
  processed_at: string;
  memory_extracted: boolean;
}

export interface FeedbackResponse {
  status: string;
  message: string;
  data: FeedbackData;
}

export interface FeedbackAsyncResponse {
  status: 'accepted';
  recommendation_id: string;
  processing: 'started';
  message: string;
}

export interface FeedbackStatusData {
  status: 'processing' | 'completed' | 'failed';
  started_at: string;
  completed_at?: string;
  failed_at?: string;
  result?: {
    recommendation_id: string;
    solubility?: number;
    solubility_unit: string;
    is_liquid_formed?: boolean;
    memories_extracted: string[];
    num_memories: number;
  };
  error?: string;
  is_update?: boolean;
  deleted_memories?: number;
}

export interface FeedbackStatusResponse {
  status: string;
  message?: string;
  data: FeedbackStatusData;
}

// ============================================
// Statistics Related Types
// ============================================

export interface SummaryStatistics {
  total_recommendations: number;
  pending_experiments: number;
  completed_experiments: number;
  cancelled: number;
  average_performance_score: number;
  liquid_formation_rate: number;
}

export interface PerformanceTrendPoint {
  date: string;
  avg_solubility: number;
  solubility_unit: string;
  avg_performance_score: number;
  experiment_count: number;
  liquid_formation_rate: number;
}

export interface TopFormulation {
  formulation: string;
  avg_performance: number;
  solubility_unit: string;
  success_count: number;
}

export interface StatisticsData {
  summary: SummaryStatistics;
  by_material: Record<string, number>;
  by_status: Record<string, number>;
  performance_trend: PerformanceTrendPoint[];
  top_formulations: TopFormulation[];
}

export interface StatisticsResponse {
  status: string;
  message: string;
  data: StatisticsData;
}

export interface PerformanceTrendResponse {
  status: string;
  message: string;
  data: PerformanceTrendPoint[];
}

// ============================================
// Memory Management Types
// ============================================

export interface MemoryItemDetail {
  title: string;
  description: string;
  content: string;
  is_from_success: boolean;
  source_task_id?: string;
  created_at: string;
  metadata: Record<string, any>;
}

export interface MemoryItemCreate {
  title: string;
  description: string;
  content: string;
  is_from_success?: boolean;
  source_task_id?: string;
  metadata?: Record<string, any>;
}

export interface MemoryItemUpdate {
  description?: string;
  content?: string;
  is_from_success?: boolean;
  metadata?: Record<string, any>;
}

export interface MemoryListData {
  items: MemoryItemDetail[];
  pagination: {
    total: number;
    page: number;
    page_size: number;
    total_pages: number;
  };
  filters: Record<string, any>;
}

export interface MemoryListResponse {
  status: string;
  message: string;
  data: MemoryListData;
}

export interface MemoryDetailResponse {
  status: string;
  message: string;
  data: MemoryItemDetail;
}

export interface MemoryCreateResponse {
  status: string;
  message: string;
  data: MemoryItemDetail;
}

export interface MemoryUpdateResponse {
  status: string;
  message: string;
  data: MemoryItemDetail;
}

export interface MemoryDeleteResponse {
  status: string;
  message: string;
  data: {
    title: string;
    deleted_at: string;
  };
}

// ============================================
// Error Response Type
// ============================================

export interface ErrorResponse {
  status: string;
  message: string;
  detail?: string;
}

// ============================================
// UI State Types
// ============================================

export interface LoadingState {
  [key: string]: boolean;
}

export interface ErrorState {
  [key: string]: string | null;
}
