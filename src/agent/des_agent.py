"""
DES Formulation Agent with ReasoningBank

This module implements the main agent for DES formulation design,
integrating ReasoningBank memory system with CoreRAG and LargeRAG tools.
"""

from typing import Dict, List, Optional, Callable
import logging
from datetime import datetime

from .reasoningbank import (
    ReasoningBank,
    MemoryRetriever,
    MemoryExtractor,
    LLMJudge,
    MemoryItem,
    MemoryQuery,
    Trajectory,
    format_memories_for_prompt,
    # New: Async feedback components
    RecommendationManager,
    FeedbackProcessor,
    Recommendation,
    ExperimentResult
)

logger = logging.getLogger(__name__)


class DESAgent:
    """
    Main agent for DES formulation design with asynchronous experimental feedback.

    NEW: The agent now supports real experimental feedback loop:
    1. Retrieve relevant memories from ReasoningBank
    2. Query CoreRAG for theoretical knowledge
    3. Query LargeRAG for literature precedents
    4. Generate DES formulation with reasoning
    5. Create persistent Recommendation record (status: PENDING)
    6. [Async] User performs experiment
    7. [Async] User submits ExperimentResult
    8. Extract data-driven memories and consolidate

    Attributes:
        llm_client: LLM for agent reasoning
        reasoning_bank: ReasoningBank instance
        retriever: MemoryRetriever instance
        extractor: MemoryExtractor instance
        judge: LLMJudge instance (optional, not used in v1)
        rec_manager: RecommendationManager for persistent storage
        feedback_processor: FeedbackProcessor for async feedback
        corerag_client: CoreRAG tool interface
        largerag_client: LargeRAG tool interface
        config: Configuration dictionary
    """

    def __init__(
        self,
        llm_client: Callable[[str], str],
        reasoning_bank: ReasoningBank,
        retriever: MemoryRetriever,
        extractor: MemoryExtractor,
        judge: LLMJudge,
        rec_manager: RecommendationManager,  # NEW: Required
        corerag_client: Optional[object] = None,
        largerag_client: Optional[object] = None,
        config: Optional[Dict] = None
    ):
        """
        Initialize DESAgent with async feedback support.

        Args:
            llm_client: Function for LLM calls
            reasoning_bank: ReasoningBank instance
            retriever: MemoryRetriever instance
            extractor: MemoryExtractor instance
            judge: LLMJudge instance (optional, for future use)
            rec_manager: RecommendationManager instance (NEW)
            corerag_client: CoreRAG tool (optional)
            largerag_client: LargeRAG tool (optional)
            config: Configuration dictionary
        """
        self.llm_client = llm_client
        self.memory = reasoning_bank
        self.retriever = retriever
        self.extractor = extractor
        self.judge = judge
        self.corerag = corerag_client
        self.largerag = largerag_client
        self.config = config or {}

        # NEW: Recommendation and feedback management
        self.rec_manager = rec_manager
        self.feedback_processor = FeedbackProcessor(self, rec_manager)

        logger.info("Initialized DESAgent with async experimental feedback support")

    def solve_task(self, task: Dict) -> Dict:
        """
        Main entry point for solving a DES formulation task.

        Args:
            task: Task dictionary with keys:
                - task_id: Unique identifier
                - description: Natural language description
                - target_material: Material to dissolve
                - target_temperature: Target temperature (°C)
                - constraints: Additional constraints

        Returns:
            Dict with keys:
                - formulation: Proposed DES formulation
                - reasoning: Explanation of design choices
                - confidence: Confidence score (0-1)
                - supporting_evidence: Literature/theory references
                - status: "success" or "failure"
        """
        task_id = task.get("task_id", f"task_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
        logger.info(f"Starting task {task_id}: {task['description'][:50]}...")

        # Initialize trajectory tracking
        trajectory_steps = []
        tool_calls = []

        # Step 1: Memory Retrieval
        logger.info("Step 1: Retrieving relevant memories")
        memories = self._retrieve_memories(task)
        trajectory_steps.append({
            "action": "retrieve_memories",
            "reasoning": f"Retrieved {len(memories)} relevant past experiences",
            "num_memories": len(memories)
        })

        # Step 2: Query Tools
        logger.info("Step 2: Querying knowledge tools")
        theory_knowledge = self._query_corerag(task) if self.corerag else None
        literature_knowledge = self._query_largerag(task) if self.largerag else None

        if theory_knowledge:
            tool_calls.append({"tool": "CoreRAG", "query": task["description"], "result": theory_knowledge})
            trajectory_steps.append({
                "action": "query_corerag",
                "reasoning": "Retrieved theoretical principles for DES design",
                "tool": "CoreRAG"
            })

        if literature_knowledge:
            tool_calls.append({"tool": "LargeRAG", "query": task["description"], "result": literature_knowledge})
            trajectory_steps.append({
                "action": "query_largerag",
                "reasoning": "Retrieved literature precedents",
                "tool": "LargeRAG"
            })

        # Step 3: Generate Formulation
        logger.info("Step 3: Generating DES formulation")
        formulation_result = self._generate_formulation(
            task, memories, theory_knowledge, literature_knowledge
        )
        trajectory_steps.append({
            "action": "generate_formulation",
            "reasoning": formulation_result.get("reasoning", ""),
            "formulation": formulation_result["formulation"]
        })

        # Step 4: Create Trajectory Record
        logger.info("Step 4: Creating trajectory record")
        trajectory = Trajectory(
            task_id=task_id,
            task_description=task["description"],
            steps=trajectory_steps,
            outcome="pending_experiment",  # NEW: Not evaluated yet, awaiting experiment
            final_result=formulation_result,
            metadata={
                "target_material": task.get("target_material"),
                "target_temperature": task.get("target_temperature"),
                "constraints": task.get("constraints", {}),
                "tool_calls": tool_calls
            }
        )

        # Step 5: Create Recommendation Record (NEW: Replaces immediate evaluation)
        logger.info("Step 5: Creating recommendation record (status: PENDING)")
        rec_id = f"REC_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{task_id}"

        recommendation = Recommendation(
            recommendation_id=rec_id,
            task=task,
            task_id=task_id,
            formulation=formulation_result["formulation"],
            reasoning=formulation_result.get("reasoning", ""),
            confidence=formulation_result.get("confidence", 0.0),
            trajectory=trajectory,
            status="PENDING",
            created_at=datetime.now().isoformat(),
            updated_at=datetime.now().isoformat()
        )

        # Save recommendation for future experimental feedback
        self.rec_manager.save_recommendation(recommendation)
        logger.info(f"Saved recommendation {rec_id} - awaiting experimental feedback")

        # Prepare return result (no immediate evaluation, no memories extracted yet)
        result = formulation_result.copy()
        result["recommendation_id"] = rec_id
        result["status"] = "PENDING"
        result["task_id"] = task_id
        result["memories_used"] = [m.title for m in memories]
        result["next_steps"] = (
            f"Recommendation {rec_id} is ready for experimental testing. "
            f"Please perform the experiment and submit feedback using "
            f"agent.submit_experiment_feedback('{rec_id}', experiment_result)."
        )

        logger.info(f"Task {task_id} completed - recommendation {rec_id} created (status: PENDING)")

        return result

    def _retrieve_memories(self, task: Dict) -> List[MemoryItem]:
        """
        Retrieve relevant memories for the task.

        Args:
            task: Task dictionary

        Returns:
            List of relevant MemoryItem objects
        """
        query = MemoryQuery(
            query_text=task["description"],
            top_k=self.config.get("memory", {}).get("retrieval_top_k", 3),
            min_similarity=self.config.get("memory", {}).get("min_similarity", 0.0)
        )

        memories = self.retriever.retrieve(query)
        logger.debug(f"Retrieved {len(memories)} memories for task")

        return memories

    def _query_corerag(self, task: Dict) -> Optional[Dict]:
        """
        Query CoreRAG for theoretical knowledge.

        Args:
            task: Task dictionary

        Returns:
            Dict with theory knowledge, or None if unavailable
        """
        if not self.corerag:
            logger.warning("CoreRAG client not available")
            return None

        try:
            # Format query for CoreRAG
            query = {
                "query": f"What are the key principles for dissolving {task['target_material']} using DES?",
                "focus": ["hydrogen_bonding", "component_selection", "molar_ratio"]
            }

            # Call CoreRAG (interface depends on actual implementation)
            result = self.corerag.query(query)
            logger.debug(f"CoreRAG returned: {str(result)[:100]}...")

            return result

        except Exception as e:
            logger.error(f"CoreRAG query failed: {e}")
            return None

    def _query_largerag(self, task: Dict) -> Optional[Dict]:
        """
        Query LargeRAG for literature precedents.

        Args:
            task: Task dictionary

        Returns:
            Dict with literature knowledge, or None if unavailable
        """
        if not self.largerag:
            logger.warning("LargeRAG client not available")
            return None

        try:
            # Format query for LargeRAG
            query = {
                "query": f"DES formulations for {task['target_material']} at {task.get('target_temperature', 25)}°C",
                "filters": {
                    "material_type": task.get("material_category", "polymer"),
                    "temperature_range": [task.get("target_temperature", 25) - 10, task.get("target_temperature", 25) + 10]
                },
                "top_k": self.config.get("tools", {}).get("largerag", {}).get("max_results", 10)
            }

            # Call LargeRAG
            result = self.largerag.query(query)
            logger.debug(f"LargeRAG returned: {str(result)[:100]}...")

            return result

        except Exception as e:
            logger.error(f"LargeRAG query failed: {e}")
            return None

    def _generate_formulation(
        self,
        task: Dict,
        memories: List[MemoryItem],
        theory: Optional[Dict],
        literature: Optional[Dict]
    ) -> Dict:
        """
        Generate DES formulation using LLM with all available knowledge.

        Args:
            task: Task dictionary
            memories: Retrieved memory items
            theory: CoreRAG theory knowledge
            literature: LargeRAG literature knowledge

        Returns:
            Dict with formulation, reasoning, confidence, etc.
        """
        # Build comprehensive prompt
        prompt = self._build_formulation_prompt(task, memories, theory, literature)

        # Call LLM
        try:
            llm_output = self.llm_client(prompt)
            logger.debug(f"LLM formulation output: {llm_output[:200]}...")
        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            return {
                "formulation": {},
                "reasoning": f"Error: {str(e)}",
                "confidence": 0.0,
                "supporting_evidence": []
            }

        # Parse LLM output
        result = self._parse_formulation_output(llm_output)

        return result

    def _build_formulation_prompt(
        self,
        task: Dict,
        memories: List[MemoryItem],
        theory: Optional[Dict],
        literature: Optional[Dict]
    ) -> str:
        """
        Build comprehensive prompt for formulation generation.

        Args:
            task: Task dictionary
            memories: Retrieved memories
            theory: Theory knowledge
            literature: Literature knowledge

        Returns:
            Formatted prompt string
        """
        prompt = "# DES Formulation Design Task\n\n"

        # Task description
        prompt += f"## Task\n{task['description']}\n\n"
        prompt += f"**Target Material:** {task['target_material']}\n"
        prompt += f"**Target Temperature:** {task.get('target_temperature', 25)}°C\n"

        constraints = task.get("constraints", {})
        if constraints:
            prompt += f"**Constraints:** {constraints}\n"

        prompt += "\n"

        # Inject memories
        if memories:
            prompt += format_memories_for_prompt(memories)
            prompt += "\n"

        # Add theory knowledge
        if theory:
            prompt += "## Theoretical Knowledge (from CoreRAG)\n\n"
            prompt += f"{theory}\n\n"

        # Add literature knowledge
        if literature:
            prompt += "## Literature Precedents (from LargeRAG)\n\n"
            prompt += f"{literature}\n\n"

        # Instructions
        prompt += """## Instructions

Based on the above information, design a DES formulation. Your output must include:

1. **HBD (Hydrogen Bond Donor)**: Component name
2. **HBA (Hydrogen Bond Acceptor)**: Component name
3. **Molar Ratio**: e.g., "1:2" (HBD:HBA)
4. **Reasoning**: Explain your design choices (2-3 sentences)
5. **Confidence**: 0.0 to 1.0
6. **Supporting Evidence**: List key facts from memory/theory/literature

Format your response as JSON:
```json
{
    "formulation": {
        "HBD": "...",
        "HBA": "...",
        "molar_ratio": "..."
    },
    "reasoning": "...",
    "confidence": 0.0,
    "supporting_evidence": ["...", "..."]
}
```
"""

        return prompt

    def _parse_formulation_output(self, llm_output: str) -> Dict:
        """
        Parse LLM output to extract formulation.

        Args:
            llm_output: Raw LLM output

        Returns:
            Structured formulation dict
        """
        import json
        import re

        # Try to extract JSON
        json_match = re.search(r'```json\s*(.*?)\s*```', llm_output, re.DOTALL)
        if json_match:
            try:
                result = json.loads(json_match.group(1))
                return result
            except json.JSONDecodeError:
                logger.warning("Failed to parse JSON from LLM output")

        # Fallback: return minimal structure
        return {
            "formulation": {},
            "reasoning": llm_output[:500],
            "confidence": 0.5,
            "supporting_evidence": []
        }

    # ===== NEW: Asynchronous Experimental Feedback Methods =====

    def submit_experiment_feedback(
        self,
        recommendation_id: str,
        experiment_result: ExperimentResult
    ) -> Dict:
        """
        Submit experimental feedback for a recommendation (NEW: Async feedback loop).

        This method completes the async feedback loop:
        1. User performs experiment based on recommendation
        2. User submits ExperimentResult with lab measurements
        3. System extracts data-driven memories
        4. System consolidates new memories into ReasoningBank

        Args:
            recommendation_id: ID of the recommendation to update
            experiment_result: ExperimentResult object with lab measurements

        Returns:
            Dict with processing results:
                - status: "success" or "error"
                - recommendation_id: The updated recommendation ID
                - performance_score: 0-10 score from experiment
                - memories_extracted: List of extracted memory titles
                - message: Human-readable status message

        Example:
            >>> exp_result = ExperimentResult(
            ...     is_liquid_formed=True,
            ...     solubility=6.5,
            ...     solubility_unit="g/L",
            ...     properties={"viscosity": "45 cP"},
            ...     notes="Clear liquid formed at room temperature"
            ... )
            >>> result = agent.submit_experiment_feedback("REC_20250116_task_001", exp_result)
            >>> print(f"Performance: {result['performance_score']}/10.0")
            >>> print(f"Extracted {len(result['memories_extracted'])} new memories")
        """
        logger.info(f"Processing experimental feedback for recommendation {recommendation_id}")

        try:
            # Step 1: Submit experimental feedback to recommendation manager
            self.rec_manager.submit_feedback(recommendation_id, experiment_result)

            # Step 2: Use FeedbackProcessor to extract memories and update ReasoningBank
            process_result = self.feedback_processor.process_feedback(recommendation_id)

            logger.info(
                f"Feedback processing completed: {process_result['num_memories']} "
                f"memories extracted (performance: {process_result['performance_score']:.1f}/10.0)"
            )

            # Auto-save if configured
            if self.config.get("memory", {}).get("auto_save", False):
                save_path = self.config["memory"]["persist_path"]
                self.memory.save(save_path)
                logger.info(f"Auto-saved memory bank to {save_path}")

            return {
                "status": "success",
                "recommendation_id": recommendation_id,
                "performance_score": process_result["performance_score"],
                "memories_extracted": process_result["memories_extracted"],
                "message": (
                    f"Experimental feedback processed successfully. "
                    f"Performance: {process_result['performance_score']:.1f}/10.0. "
                    f"Extracted {process_result['num_memories']} new memories."
                )
            }

        except Exception as e:
            logger.error(f"Failed to process experimental feedback: {e}")
            return {
                "status": "error",
                "recommendation_id": recommendation_id,
                "message": f"Error processing feedback: {str(e)}"
            }

    def load_historical_recommendations(
        self,
        data_path: str,
        reprocess: bool = True
    ) -> Dict:
        """
        Load historical recommendations from another system instance (NEW: Cross-instance reuse).

        This enables transferring experimental knowledge between different system instances:
        - System A generates recommendations + collects experiments
        - System B loads System A's data and learns from it
        - Version-aware data format ensures backward compatibility

        Args:
            data_path: Path to directory containing recommendations.json or individual REC_*.json files
            reprocess: If True, re-extract memories with current extraction logic (default: True)
                      If False, only load existing memories without reprocessing

        Returns:
            Dict with loading results:
                - status: "success" or "error"
                - num_loaded: Number of recommendations loaded
                - num_reprocessed: Number re-processed with current logic
                - memories_added: Total memories added to ReasoningBank
                - message: Human-readable status

        Example:
            >>> # Load data from System A into System B
            >>> result = agent_B.load_historical_recommendations(
            ...     data_path="/path/to/system_A/recommendations/",
            ...     reprocess=True  # Re-extract with System B's logic
            ... )
            >>> print(f"Loaded {result['num_loaded']} recommendations")
            >>> print(f"Added {result['memories_added']} memories to System B")
        """
        logger.info(f"Loading historical recommendations from {data_path}")

        try:
            import os
            import json
            from pathlib import Path

            data_dir = Path(data_path)
            if not data_dir.exists():
                raise FileNotFoundError(f"Data path not found: {data_path}")

            num_loaded = 0
            num_reprocessed = 0
            total_memories = 0

            # Load all recommendation JSON files
            rec_files = list(data_dir.glob("REC_*.json"))

            for rec_file in rec_files:
                try:
                    with open(rec_file, "r", encoding="utf-8") as f:
                        rec_data = json.load(f)

                    # Convert to Recommendation object (version-aware deserialization)
                    rec = Recommendation.from_dict(rec_data)

                    # Only process COMPLETED recommendations with experimental feedback
                    if rec.status == "COMPLETED" and rec.experiment_result is not None:
                        num_loaded += 1

                        if reprocess:
                            # Re-extract memories with current extraction logic
                            logger.info(f"Reprocessing {rec.recommendation_id} with current logic")

                            new_memories = self.extractor.extract_from_experiment(
                                rec.trajectory,
                                rec.experiment_result
                            )

                            if new_memories:
                                self.memory.consolidate(new_memories)
                                total_memories += len(new_memories)
                                num_reprocessed += 1
                                logger.info(
                                    f"Extracted {len(new_memories)} memories from {rec.recommendation_id}"
                                )
                        else:
                            # Just load existing memories (if stored in trajectory metadata)
                            existing_memories = rec.trajectory.metadata.get("extracted_memories", [])
                            total_memories += len(existing_memories)
                            logger.info(
                                f"Loaded {len(existing_memories)} existing memories from {rec.recommendation_id}"
                            )

                    else:
                        logger.debug(
                            f"Skipping {rec.recommendation_id} (status={rec.status}, "
                            f"has_feedback={rec.experiment_result is not None})"
                        )

                except Exception as e:
                    logger.warning(f"Failed to load {rec_file}: {e}")
                    continue

            # Auto-save if configured
            if self.config.get("memory", {}).get("auto_save", False):
                save_path = self.config["memory"]["persist_path"]
                self.memory.save(save_path)
                logger.info(f"Auto-saved memory bank to {save_path}")

            logger.info(
                f"Historical data loading complete: {num_loaded} recommendations loaded, "
                f"{num_reprocessed} reprocessed, {total_memories} memories added"
            )

            return {
                "status": "success",
                "num_loaded": num_loaded,
                "num_reprocessed": num_reprocessed,
                "memories_added": total_memories,
                "message": (
                    f"Successfully loaded {num_loaded} recommendations. "
                    f"Reprocessed {num_reprocessed} with current logic. "
                    f"Added {total_memories} memories to ReasoningBank."
                )
            }

        except Exception as e:
            logger.error(f"Failed to load historical recommendations: {e}")
            return {
                "status": "error",
                "num_loaded": 0,
                "num_reprocessed": 0,
                "memories_added": 0,
                "message": f"Error loading historical data: {str(e)}"
            }


# Example usage and testing
if __name__ == "__main__":
    # This will be implemented in examples/example_des_task.py
    pass
