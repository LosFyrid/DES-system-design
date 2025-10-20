"""
DES Formulation Agent with ReasoningBank

This module implements the main agent for DES formulation design,
integrating ReasoningBank memory system with CoreRAG and LargeRAG tools.
"""

from typing import Dict, List, Optional, Callable, Tuple
import logging
from datetime import datetime
import asyncio
import json
import re

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

    # ===== ReAct Core Methods =====

    def _think(self, task: Dict, knowledge_state: Dict, iteration: int) -> Dict:
        """
        THINK phase: Analyze current knowledge state and decide next action.

        This is the planning/reasoning step where the LLM examines what information
        has been gathered so far and decides what to do next.

        Args:
            task: Task specification
            knowledge_state: Current accumulated knowledge
            iteration: Current iteration number

        Returns:
            Dict with:
                - action: Next action to take
                - reasoning: Explanation of the decision
                - information_gaps: What information is still missing
        """
        # Build thinking prompt
        max_iterations = self.config.get("agent", {}).get("max_iterations", 8)
        remaining_iterations = max_iterations - iteration
        progress_pct = int((iteration / max_iterations) * 100)

        # Determine iteration stage
        if progress_pct < 40:
            stage = "Early"
        elif progress_pct < 75:
            stage = "Mid"
        else:
            stage = "Late"

        # Summarize accumulated knowledge
        theory_summary = f"{knowledge_state['num_theory_queries']} queries made" if knowledge_state['num_theory_queries'] > 0 else "Not retrieved"
        literature_summary = f"{knowledge_state['num_literature_queries']} queries made" if knowledge_state['num_literature_queries'] > 0 else "Not retrieved"

        # NEW: Failure tracking summary
        failed_theory = knowledge_state.get('failed_theory_attempts', 0)
        failed_literature = knowledge_state.get('failed_literature_attempts', 0)

        # Format memory summary
        memory_summary = ""
        if knowledge_state['memories'] and len(knowledge_state['memories']) > 0:
            memory_summary = "\n**Retrieved Memories Summary**:\n"
            for i, mem in enumerate(knowledge_state['memories'][:3], 1):
                solubility = mem.metadata.get('solubility', 'N/A')
                sol_unit = mem.metadata.get('solubility_unit', '')
                memory_summary += f"  {i}. {mem.title[:80]}... (溶解度: {solubility} {sol_unit})\n"
            if len(knowledge_state['memories']) > 3:
                memory_summary += f"  ... and {len(knowledge_state['memories']) - 3} more\n"

        think_prompt = f"""You are a DES (Deep Eutectic Solvent) formulation expert planning your research approach.

**Task**: {task['description']}
**Target Material**: {task['target_material']}
**Target Temperature**: {task.get('target_temperature', 25)}°C
**Constraints**: {task.get('constraints', {})}

**Progress**: Iteration {iteration}/{max_iterations} ({progress_pct}% complete, {remaining_iterations} remaining) - **{stage} Stage**

**Current Knowledge State**:
- Memories retrieved: {knowledge_state['memories_retrieved']} ({len(knowledge_state['memories'] or [])} items)
{memory_summary}
- Theoretical knowledge (CoreRAG): {theory_summary} (failed attempts: {failed_theory})
- Literature knowledge (LargeRAG): {literature_summary} (failed attempts: {failed_literature})
- Formulation candidates generated: {len(knowledge_state['formulation_candidates'])}
- Previous observations: {len(knowledge_state['observations'])}

**Recent Observations**:
{self._format_observations(knowledge_state['observations'][-2:] if len(knowledge_state['observations']) > 0 else [])}

**Available Actions**:
1. **retrieve_memories** - Get past experiences from ReasoningBank (validated experimental data)
2. **query_theory** - Query CoreRAG ontology for theoretical principles
3. **query_literature** - Query LargeRAG for literature data
4. **query_parallel** - Query both CoreRAG and LargeRAG simultaneously
5. **generate_formulation** - Generate DES formulation from accumulated knowledge
6. **refine_formulation** - Refine existing formulation with more information
7. **finish** - Complete task (only if formulation is ready)

**Tool Characteristics**:
- **ReasoningBank (retrieve_memories)**: Instant retrieval of validated past experiments - **MOST RELIABLE**
- **LargeRAG (query_literature)**: Fast vector search (~1-2 seconds) across 10,000+ papers
- **CoreRAG (query_theory)**: Deep ontology reasoning (~5-10 minutes per query)

**CRITICAL: Memory-First Strategy**:
1. **ALWAYS retrieve memories FIRST** (in iteration 1) if not yet retrieved - memories contain validated experimental data
2. Memories from real experiments are the **MOST RELIABLE** knowledge source
3. Only query CoreRAG/LargeRAG if memories are insufficient or missing critical details

**Research Requirements**:
- **Preferred**: Memories + Theory (CoreRAG) + Literature (LargeRAG)
- **Acceptable**: Memories + LLM parametric knowledge (if tools unavailable)
- **Minimum**: High-quality memories from similar experiments

**CoreRAG Usage Guidelines**:
- CoreRAG is NECESSARY (DES design needs theoretical basis), but takes 5-10 minutes
- **Use thoughtfully**: Craft comprehensive, well-structured queries to maximize information gain per query
- **Avoid repeated similar queries**: Plan what theoretical knowledge you need, then query ONCE with a complete question
- Good query: "What are the key principles for cellulose dissolution via DES? Include hydrogen bonding mechanisms, component selection criteria, and molar ratio considerations."
- Poor query: Multiple narrow queries like "What is hydrogen bonding?" then "What about molar ratios?" (wasteful)

**Decision Guidelines by Stage**:
- **Early ({stage == 'Early' and '✓' or '✗'})**:
  - **Priority 1**: Retrieve memories if not yet done
  - **Priority 2**: Query literature/theory only if memories insufficient
- **Mid ({stage == 'Mid' and '✓' or '✗'})**: Ensure sufficient knowledge from memories + available tools
- **Late ({stage == 'Late' and '✓' or '✗'})**: Must generate formulation soon. If you have memories + any additional knowledge → generate now

**STRICT Anti-Loop Rules**:
- **STOP after 2 consecutive failures**: If a tool fails 2 times in a row → STOP trying, move to alternative action
- **Failed tool tracking**: CoreRAG failed {failed_theory} times, LargeRAG failed {failed_literature} times
- **If both tools unavailable ({failed_theory >= 2 and failed_literature >= 2})**: RELY ON MEMORIES + LLM parametric knowledge and generate formulation immediately
- **DO NOT repeat the same action if result is unchanged**: (e.g., retrieve_memories returns 0 twice → move on)
- **Progress awareness**: At {progress_pct}% complete, prioritize actions that move towards formulation generation

**Your Task**:
Given your current progress ({iteration}/{max_iterations}, {stage} stage), analyze the knowledge state and decide the SINGLE most valuable next action.

Output JSON:
{{
    "action": "action_name",
    "reasoning": "Why this action is the best next step (2-3 sentences)",
    "information_gaps": ["gap1", "gap2"]  // What critical info is still missing
}}
"""

        try:
            response = self.llm_client(think_prompt)
            thought = self._parse_json_response(response)

            # Validate action
            valid_actions = [
                "retrieve_memories", "query_theory", "query_literature",
                "query_parallel", "generate_formulation", "refine_formulation", "finish"
            ]

            if thought.get("action") not in valid_actions:
                logger.warning(f"Invalid action '{thought.get('action')}', defaulting to retrieve_memories")
                thought["action"] = "retrieve_memories"

            return thought

        except Exception as e:
            logger.error(f"Think phase failed: {e}")
            # Fallback: simple heuristic
            if not knowledge_state["memories_retrieved"]:
                return {
                    "action": "retrieve_memories",
                    "reasoning": "Starting with memory retrieval (fallback decision)",
                    "information_gaps": ["All information"]
                }
            elif not knowledge_state["theory_knowledge"] and not knowledge_state["literature_knowledge"]:
                return {
                    "action": "query_parallel",
                    "reasoning": "Need both theory and literature (fallback decision)",
                    "information_gaps": ["Theory", "Literature"]
                }
            else:
                return {
                    "action": "generate_formulation",
                    "reasoning": "Have sufficient information (fallback decision)",
                    "information_gaps": []
                }

    def _act(self, action: str, task: Dict, knowledge_state: Dict, tool_calls: List) -> Dict:
        """
        ACT phase: Execute the chosen action.

        Args:
            action: Action to execute
            task: Task specification
            knowledge_state: Current knowledge state (will be updated in-place)
            tool_calls: List to append tool call records

        Returns:
            Dict with:
                - action: Action that was executed
                - success: Whether action succeeded
                - data: Retrieved/generated data
                - summary: Human-readable summary
        """
        logger.info(f"[ACT] Executing action: {action}")

        if action == "retrieve_memories":
            memories = self._retrieve_memories(task)
            knowledge_state["memories"] = memories
            knowledge_state["memories_retrieved"] = True
            return {
                "action": "retrieve_memories",
                "success": True,
                "data": memories,
                "summary": f"Retrieved {len(memories)} relevant memories from past experiences"
            }

        elif action == "query_theory":
            theory = self._query_corerag(task, knowledge_state)
            if theory:
                knowledge_state["theory_knowledge"].append(theory)  # Accumulate
                knowledge_state["num_theory_queries"] += 1
                tool_calls.append({"tool": "CoreRAG", "query": task["description"], "result": theory})
            else:
                knowledge_state["failed_theory_attempts"] += 1  # Track failure
            return {
                "action": "query_theory",
                "success": theory is not None,
                "data": theory,
                "summary": f"Retrieved theoretical knowledge from CoreRAG ontology (query #{knowledge_state['num_theory_queries']})" if theory else "CoreRAG query failed"
            }

        elif action == "query_literature":
            literature = self._query_largerag(task, knowledge_state)
            if literature:
                knowledge_state["literature_knowledge"].append(literature)  # Accumulate
                knowledge_state["num_literature_queries"] += 1
                tool_calls.append({"tool": "LargeRAG", "query": task["description"], "result": literature})
            else:
                knowledge_state["failed_literature_attempts"] += 1  # Track failure
            return {
                "action": "query_literature",
                "success": literature is not None,
                "data": literature,
                "summary": f"Retrieved literature precedents from LargeRAG (query #{knowledge_state['num_literature_queries']})" if literature else "LargeRAG query failed"
            }

        elif action == "query_parallel":
            # Parallel query both tools
            theory, literature = self._query_tools_parallel(task, knowledge_state)

            if theory:
                knowledge_state["theory_knowledge"].append(theory)  # Accumulate
                knowledge_state["num_theory_queries"] += 1
                tool_calls.append({"tool": "CoreRAG", "query": task["description"], "result": theory})
            else:
                knowledge_state["failed_theory_attempts"] += 1

            if literature:
                knowledge_state["literature_knowledge"].append(literature)  # Accumulate
                knowledge_state["num_literature_queries"] += 1
                tool_calls.append({"tool": "LargeRAG", "query": task["description"], "result": literature})
            else:
                knowledge_state["failed_literature_attempts"] += 1

            return {
                "action": "query_parallel",
                "success": (theory is not None) or (literature is not None),
                "data": {"theory": theory, "literature": literature},
                "summary": f"Parallel query: CoreRAG {'✓ (query #' + str(knowledge_state['num_theory_queries']) + ')' if theory else '✗'}, LargeRAG {'✓ (query #' + str(knowledge_state['num_literature_queries']) + ')' if literature else '✗'}"
            }

        elif action == "generate_formulation":
            # Ensure memories are retrieved
            if not knowledge_state["memories_retrieved"]:
                knowledge_state["memories"] = self._retrieve_memories(task)
                knowledge_state["memories_retrieved"] = True

            formulation = self._generate_formulation(
                task,
                knowledge_state["memories"] or [],
                knowledge_state["theory_knowledge"],
                knowledge_state["literature_knowledge"]
            )

            knowledge_state["formulation_candidates"].append(formulation)
            return {
                "action": "generate_formulation",
                "success": True,
                "data": formulation,
                "summary": f"Generated formulation: {formulation['formulation'].get('HBD', '?')}:{formulation['formulation'].get('HBA', '?')} (confidence: {formulation.get('confidence', 0):.2f})"
            }

        elif action == "refine_formulation":
            # Generate additional candidate with current knowledge
            if not knowledge_state["formulation_candidates"]:
                # No formulation to refine, generate new one
                return self._act("generate_formulation", task, knowledge_state, tool_calls)

            formulation = self._generate_formulation(
                task,
                knowledge_state["memories"] or [],
                knowledge_state["theory_knowledge"],
                knowledge_state["literature_knowledge"]
            )

            knowledge_state["formulation_candidates"].append(formulation)
            return {
                "action": "refine_formulation",
                "success": True,
                "data": formulation,
                "summary": f"Refined formulation (now have {len(knowledge_state['formulation_candidates'])} candidates)"
            }

        else:
            logger.warning(f"Unknown action: {action}")
            return {
                "action": action,
                "success": False,
                "data": None,
                "summary": f"Unknown action: {action}"
            }

    def _observe(self, action_result: Dict, knowledge_state: Dict) -> Dict:
        """
        OBSERVE phase: Summarize action results and integrate into knowledge state.

        This phase analyzes what was learned from the action and updates the
        knowledge state accordingly. It also identifies remaining information gaps.

        Args:
            action_result: Result from _act method
            knowledge_state: Current knowledge state (for context)

        Returns:
            Dict with:
                - summary: Observation summary
                - knowledge_updated: What knowledge was updated
                - information_sufficient: Whether we have enough info to generate formulation
        """
        observation = {
            "action": action_result["action"],
            "success": action_result["success"],
            "summary": "",
            "knowledge_updated": [],
            "information_sufficient": False
        }

        # Analyze what was gained
        if action_result["action"] == "retrieve_memories" and action_result["success"]:
            num_memories = len(action_result["data"])
            observation["summary"] = f"Gained {num_memories} past experiences. "
            observation["knowledge_updated"].append("memories")

            if num_memories > 0:
                observation["summary"] += "These memories provide validated strategies for similar tasks."
            else:
                observation["summary"] += "No past experiences found - this is a novel task."

        elif action_result["action"] == "query_parallel":
            # Special handling for parallel query - check both theory and literature results
            theory_available = len(knowledge_state["theory_knowledge"]) > 0
            literature_available = len(knowledge_state["literature_knowledge"]) > 0

            theory_status = f"✓ ({knowledge_state['num_theory_queries']} total)" if theory_available else "✗"
            lit_status = f"✓ ({knowledge_state['num_literature_queries']} total)" if literature_available else "✗"

            observation["summary"] = f"Parallel query results: CoreRAG {theory_status}, LargeRAG {lit_status}. "

            # Update knowledge_updated based on what we got this time
            if action_result["data"]["theory"]:
                observation["knowledge_updated"].append("theory")
            if action_result["data"]["literature"]:
                observation["knowledge_updated"].append("literature")

            # Detailed explanation of what we gained
            if action_result["data"]["theory"] and action_result["data"]["literature"]:
                observation["summary"] += "Successfully retrieved both theoretical principles and literature precedents. "
            elif action_result["data"]["literature"]:
                observation["summary"] += "Successfully retrieved literature precedents from LargeRAG. "
            elif action_result["data"]["theory"]:
                observation["summary"] += "Successfully retrieved theoretical knowledge from CoreRAG. "
            else:
                observation["summary"] += "Both queries returned no results - will rely on available knowledge."

        elif action_result["action"] == "query_theory":
            if action_result["data"]:
                observation["summary"] = f"Gained theoretical knowledge from CoreRAG ontology (query #{knowledge_state['num_theory_queries']}). "
                observation["knowledge_updated"].append("theory")
                observation["summary"] += "Understand chemical principles for component selection."
            else:
                observation["summary"] = "CoreRAG query returned no results (tool unavailable or query failed). "
                observation["summary"] += "Will proceed with available knowledge sources."

        elif action_result["action"] == "query_literature":
            if action_result["data"]:
                observation["summary"] = f"Gained literature precedents from LargeRAG (query #{knowledge_state['num_literature_queries']}). "
                observation["knowledge_updated"].append("literature")
                observation["summary"] += "Have experimental data from published research."
            else:
                observation["summary"] = "LargeRAG query returned no results (tool unavailable or query failed). "
                observation["summary"] += "Proceeding without external knowledge sources."

        elif action_result["action"] in ["generate_formulation", "refine_formulation"]:
            formulation = action_result["data"]
            confidence = formulation.get("confidence", 0.0)
            observation["summary"] = f"Generated formulation with confidence {confidence:.2f}. "
            observation["knowledge_updated"].append("formulation")

            if confidence >= 0.75:
                observation["summary"] += "High confidence - formulation is ready."
                observation["information_sufficient"] = True
            elif confidence >= 0.5:
                observation["summary"] += "Moderate confidence - may benefit from more information."
            else:
                observation["summary"] += "Low confidence - need more knowledge or different approach."

        # Check overall information sufficiency
        has_knowledge = (
            knowledge_state["memories_retrieved"] or
            len(knowledge_state["theory_knowledge"]) > 0 or
            len(knowledge_state["literature_knowledge"]) > 0
        )

        has_formulation = len(knowledge_state["formulation_candidates"]) > 0

        if has_formulation and knowledge_state["formulation_candidates"][0].get("confidence", 0) >= 0.6:
            observation["information_sufficient"] = True

        return observation

    # ===== Helper Methods =====

    def _format_observations(self, observations: List[Dict]) -> str:
        """Format recent observations for display in prompts."""
        if not observations:
            return "(No observations yet)"

        formatted = []
        for i, obs in enumerate(observations, 1):
            formatted.append(f"{i}. {obs.get('summary', 'No summary')}")

        return "\n".join(formatted)

    def _parse_json_response(self, llm_output: str) -> Dict:
        """Parse JSON from LLM response with multiple fallback strategies."""
        # Try to extract JSON block
        json_match = re.search(r'```json\s*(.*?)\s*```', llm_output, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass

        # Try to find any JSON object
        json_match = re.search(r'\{.*?\}', llm_output, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(0))
            except json.JSONDecodeError:
                pass

        # Fallback: return empty dict
        logger.warning("Could not parse JSON from LLM output")
        return {}

    def _query_tools_parallel(self, task: Dict, knowledge_state: Dict) -> Tuple[Optional[Dict], Optional[Dict]]:
        """
        Query CoreRAG and LargeRAG in parallel for efficiency.

        Returns:
            (theory_knowledge, literature_knowledge)
        """
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(self._query_tools_parallel_async(task, knowledge_state))
            loop.close()
            return result
        except Exception as e:
            logger.error(f"Parallel query failed: {e}")
            # Fallback to sequential
            theory = self._query_corerag(task, knowledge_state)
            literature = self._query_largerag(task, knowledge_state)
            return theory, literature

    async def _query_tools_parallel_async(self, task: Dict, knowledge_state: Dict) -> Tuple[Optional[Dict], Optional[Dict]]:
        """Async version of parallel tool query."""
        loop = asyncio.get_event_loop()

        # Create tasks
        tasks = []
        if self.corerag:
            tasks.append(loop.run_in_executor(None, self._query_corerag, task, knowledge_state))
        else:
            tasks.append(asyncio.sleep(0, result=None))

        if self.largerag:
            tasks.append(loop.run_in_executor(None, self._query_largerag, task, knowledge_state))
        else:
            tasks.append(asyncio.sleep(0, result=None))

        # Execute in parallel
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Handle results
        theory = results[0] if not isinstance(results[0], Exception) else None
        literature = results[1] if not isinstance(results[1], Exception) else None

        return theory, literature

    def solve_task(self, task: Dict) -> Dict:
        """
        Main entry point for solving a DES formulation task using ReAct loop.

        NEW: ReAct (Reasoning-Acting) paradigm:
        - Think: Analyze current knowledge state and decide next action
        - Act: Execute the chosen action (query tools, generate formulation)
        - Observe: Summarize results and update knowledge state

        This creates a cumulative information-building process similar to deep research agents.

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
                - status: "PENDING"
                - iterations_used: Number of ReAct iterations
        """
        task_id = task.get("task_id", f"task_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
        logger.info(f"[ReAct Agent] Starting task {task_id}: {task['description'][:50]}...")

        # Initialize knowledge state
        knowledge_state = {
            "memories": None,
            "memories_retrieved": False,
            "theory_knowledge": [],  # Changed: List to accumulate all theory queries
            "literature_knowledge": [],  # Changed: List to accumulate all literature queries
            "formulation_candidates": [],
            "observations": [],
            "information_gaps": [],  # Track what we still need to know
            "num_theory_queries": 0,  # Track number of CoreRAG queries
            "num_literature_queries": 0,  # Track number of LargeRAG queries
            "failed_theory_attempts": 0,  # NEW: Track failed CoreRAG attempts
            "failed_literature_attempts": 0,  # NEW: Track failed LargeRAG attempts
        }

        # Initialize trajectory tracking
        trajectory_steps = []
        tool_calls = []

        # ReAct loop parameters
        max_iterations = self.config.get("agent", {}).get("max_iterations", 8)
        iteration = 0
        task_complete = False

        # ===== ReAct Loop =====
        while iteration < max_iterations and not task_complete:
            iteration += 1
            logger.info(f"\n{'='*60}")
            logger.info(f"[ReAct Iteration {iteration}/{max_iterations}]")
            logger.info(f"{'='*60}")

            # THINK: Decide next action based on current knowledge state
            thought = self._think(task, knowledge_state, iteration)
            logger.info(f"[THINK] {thought['reasoning']}")
            logger.info(f"[THINK] Next action: {thought['action']}")

            trajectory_steps.append({
                "iteration": iteration,
                "phase": "think",
                "reasoning": thought["reasoning"],
                "action": thought["action"],
                "information_gaps": thought.get("information_gaps", [])
            })

            # Check if ready to finish
            if thought["action"] == "finish":
                logger.info("[THINK] Decision: Task complete, ready to finalize")
                task_complete = True
                break

            # ACT: Execute the chosen action
            action_result = self._act(thought["action"], task, knowledge_state, tool_calls)
            logger.info(f"[ACT] Executed: {thought['action']}")

            trajectory_steps.append({
                "iteration": iteration,
                "phase": "act",
                "action": thought["action"],
                "result_summary": action_result.get("summary", "")
            })

            # OBSERVE: Summarize and integrate new information
            observation = self._observe(action_result, knowledge_state)
            logger.info(f"[OBSERVE] {observation['summary']}")

            knowledge_state["observations"].append(observation)
            trajectory_steps.append({
                "iteration": iteration,
                "phase": "observe",
                "observation": observation["summary"],
                "knowledge_updated": observation.get("knowledge_updated", [])
            })

        # ===== Finalize Formulation =====
        logger.info(f"\n[ReAct Agent] Finalizing after {iteration} iterations")

        # If no formulation generated yet, generate now
        if not knowledge_state.get("formulation_candidates"):
            logger.info("[Final] Generating formulation from accumulated knowledge")
            if not knowledge_state["memories_retrieved"]:
                knowledge_state["memories"] = self._retrieve_memories(task)
                knowledge_state["memories_retrieved"] = True

            formulation_result = self._generate_formulation(
                task,
                knowledge_state["memories"] or [],
                knowledge_state["theory_knowledge"],
                knowledge_state["literature_knowledge"]
            )
        else:
            # Use best candidate
            formulation_result = knowledge_state["formulation_candidates"][0]

        # ===== Create Trajectory Record =====
        trajectory = Trajectory(
            task_id=task_id,
            task_description=task["description"],
            steps=trajectory_steps,
            outcome="pending_experiment",
            final_result=formulation_result,
            metadata={
                "target_material": task.get("target_material"),
                "target_temperature": task.get("target_temperature"),
                "constraints": task.get("constraints", {}),
                "tool_calls": tool_calls,
                "iterations_used": iteration,
                "react_mode": True,
                "final_knowledge_state": {
                    "had_memories": knowledge_state["memories_retrieved"],
                    "had_theory": len(knowledge_state["theory_knowledge"]) > 0,
                    "had_literature": len(knowledge_state["literature_knowledge"]) > 0,
                    "num_theory_queries": knowledge_state["num_theory_queries"],
                    "num_literature_queries": knowledge_state["num_literature_queries"],
                }
            }
        )

        # ===== Create Recommendation Record =====
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

        self.rec_manager.save_recommendation(recommendation)
        logger.info(f"[ReAct Agent] Saved recommendation {rec_id}")

        # ===== Prepare Return Result =====
        result = formulation_result.copy()
        result["recommendation_id"] = rec_id
        result["status"] = "PENDING"
        result["task_id"] = task_id
        result["iterations_used"] = iteration
        result["memories_used"] = [m.title for m in (knowledge_state["memories"] or [])]
        result["information_sources"] = {
            "memories": knowledge_state["memories_retrieved"],
            "theory": len(knowledge_state["theory_knowledge"]) > 0,
            "literature": len(knowledge_state["literature_knowledge"]) > 0
        }
        result["next_steps"] = (
            f"Recommendation {rec_id} is ready for experimental testing. "
            f"Submit feedback using agent.submit_experiment_feedback('{rec_id}', experiment_result)."
        )

        logger.info(f"[ReAct Agent] Task {task_id} completed in {iteration} iterations")
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

    def _query_corerag(self, task: Dict, knowledge_state: Dict) -> Optional[Dict]:
        """
        Query CoreRAG for theoretical knowledge using LLM-generated query.

        Args:
            task: Task dictionary
            knowledge_state: Current knowledge state (to generate informed queries)

        Returns:
            Dict with theory knowledge, or None if unavailable
        """
        if not self.corerag:
            logger.warning("CoreRAG client not available")
            return None

        try:
            # Let LLM generate the query based on current knowledge state
            num_prev_queries = knowledge_state["num_theory_queries"]

            # Summarize what we already know
            prev_theory_summary = ""
            if knowledge_state["theory_knowledge"]:
                prev_theory_summary = f"\n**Previous theory queries ({num_prev_queries} total):**\n"
                for i, theory in enumerate(knowledge_state["theory_knowledge"][-2:], start=max(1, num_prev_queries-1)):
                    prev_theory_summary += f"Query {i}: Retrieved theoretical knowledge\n"

            literature_summary = ""
            if knowledge_state["literature_knowledge"]:
                literature_summary = f"\n**Literature knowledge acquired:** {len(knowledge_state['literature_knowledge'])} queries completed"

            query_gen_prompt = f"""You are generating a query for CoreRAG (theoretical ontology database) to support DES formulation design.

**Task**: {task['description']}
**Target Material**: {task['target_material']}
**Temperature**: {task.get('target_temperature', 25)}°C
**Constraints**: {task.get('constraints', {})}

**Current Knowledge State**:
- Theory queries completed: {num_prev_queries}
- Literature queries completed: {knowledge_state['num_literature_queries']}
{prev_theory_summary}
{literature_summary}

**Your Goal**: Generate a comprehensive, well-structured CoreRAG query to retrieve theoretical knowledge.

**Guidelines**:
- If this is the FIRST theory query (query #{num_prev_queries + 1}): Ask for comprehensive theoretical foundations (hydrogen bonding, component selection, molar ratios, temperature effects)
- If this is a SUBSEQUENT query: Ask for complementary theoretical insights not covered in previous queries
- Be specific and detailed to maximize information gain
- CoreRAG takes 5-10 minutes per query, so make it count!

Output ONLY the query text (no JSON, no explanation):"""

            query_text = self.llm_client(query_gen_prompt).strip()
            # Remove quotes if LLM added them
            query_text = query_text.strip('"').strip("'")

            logger.info(f"[CoreRAG Query #{num_prev_queries + 1}] LLM generated: {query_text[:100]}...")

            # Format query for CoreRAG
            query = {
                "query": query_text,
                "focus": ["hydrogen_bonding", "component_selection", "molar_ratio", "temperature_effects"]
            }

            # Call CoreRAG
            result = self.corerag.query(query)
            logger.debug(f"CoreRAG returned: {str(result)[:100]}...")

            return result

        except Exception as e:
            logger.error(f"CoreRAG query failed: {e}")
            return None

    def _query_largerag(self, task: Dict, knowledge_state: Dict) -> Optional[Dict]:
        """
        Query LargeRAG for literature precedents using LLM-generated query.

        Args:
            task: Task dictionary
            knowledge_state: Current knowledge state (to generate diverse queries)

        Returns:
            Dict with literature knowledge, or None if unavailable
        """
        if not self.largerag:
            logger.warning("LargeRAG client not available")
            return None

        try:
            num_prev_queries = knowledge_state["num_literature_queries"]

            # Summarize previous queries to avoid repetition
            prev_lit_summary = ""
            if knowledge_state["literature_knowledge"]:
                prev_lit_summary = f"\n**Previous literature queries ({num_prev_queries} total):**\n"
                prev_lit_summary += f"Already retrieved {num_prev_queries * 10} documents from literature.\n"
                prev_lit_summary += "Generate a DIFFERENT query to explore new angles (e.g., different keywords, component variations, property focus)."

            theory_summary = ""
            if knowledge_state["theory_knowledge"]:
                theory_summary = f"\n**Theoretical knowledge available:** {len(knowledge_state['theory_knowledge'])} theory queries completed"

            query_gen_prompt = f"""You are generating a query for LargeRAG (literature database with 10,000+ papers) to support DES formulation design.

**Task**: {task['description']}
**Target Material**: {task['target_material']}
**Temperature**: {task.get('target_temperature', 25)}°C
**Constraints**: {task.get('constraints', {})}

**Current Knowledge State**:
- Literature queries completed: {num_prev_queries}
- Theory queries completed: {knowledge_state['num_theory_queries']}
{prev_lit_summary}
{theory_summary}

**Your Goal**: Generate a literature search query to find relevant DES formulations and experimental data.

**Guidelines**:
- Query #{num_prev_queries + 1} of literature search
- If first query: Search for direct DES formulation examples
- If subsequent query: Explore DIFFERENT angles (e.g., component variations, property data, dissolution mechanisms, alternative formulations)
- **IMPORTANT**: Make each query DIFFERENT from previous ones to maximize information coverage
- Use specific keywords relevant to DES and {task['target_material']}

Output ONLY the query text (no JSON, no explanation):"""

            query_text = self.llm_client(query_gen_prompt).strip()
            # Remove quotes if LLM added them
            query_text = query_text.strip('"').strip("'")

            logger.info(f"[LargeRAG Query #{num_prev_queries + 1}] LLM generated: {query_text[:100]}...")

            # Format query for LargeRAG
            query = {
                "query": query_text,
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
        theory_list: List[Dict],  # Changed: Now a list of all theory queries
        literature_list: List[Dict]  # Changed: Now a list of all literature queries
    ) -> Dict:
        """
        Generate DES formulation using LLM with all available knowledge.

        Args:
            task: Task dictionary
            memories: Retrieved memory items
            theory_list: List of all CoreRAG theory knowledge retrieved
            literature_list: List of all LargeRAG literature knowledge retrieved

        Returns:
            Dict with formulation, reasoning, confidence, etc.
        """
        # Build comprehensive prompt
        prompt = self._build_formulation_prompt(task, memories, theory_list, literature_list)

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
        theory_list: List[Dict],  # Changed
        literature_list: List[Dict]  # Changed
    ) -> str:
        """
        Build comprehensive prompt for formulation generation.

        Args:
            task: Task dictionary
            memories: Retrieved memories
            theory_list: List of theory knowledge
            literature_list: List of literature knowledge

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

        # Add all accumulated theory knowledge
        if theory_list:
            prompt += f"## Theoretical Knowledge (from CoreRAG - {len(theory_list)} queries)\n\n"
            for i, theory in enumerate(theory_list, 1):
                prompt += f"### Theory Query {i}:\n{theory}\n\n"

        # Add all accumulated literature knowledge
        if literature_list:
            prompt += f"## Literature Precedents (from LargeRAG - {len(literature_list)} queries)\n\n"
            for i, literature in enumerate(literature_list, 1):
                prompt += f"### Literature Query {i}:\n{literature}\n\n"

        # Instructions - Support both binary and multi-component DES
        num_components = task.get("num_components", 2)  # Default to binary (2-component) DES

        if num_components == 2:
            # Binary DES (traditional format)
            prompt += """## Instructions

Based on the above information, design a **binary DES formulation** (2 components). Your output must include:

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
        else:
            # Multi-component DES (ternary, quaternary, etc.)
            prompt += f"""## Instructions

Based on the above information, design a **{num_components}-component DES formulation** (multi-component eutectic system). Your output must include:

1. **Components**: List of {num_components} components with their roles (HBD/HBA/neutral)
2. **Molar Ratio**: Ratio between all components (e.g., "1:2:1" for ternary)
3. **Reasoning**: Explain your design choices, especially why multiple components are beneficial (3-4 sentences)
4. **Confidence**: 0.0 to 1.0
5. **Supporting Evidence**: List key facts from memory/theory/literature
6. **Synergy Explanation**: How do the multiple components work together?

Format your response as JSON:
```json
{{
    "formulation": {{
        "components": [
            {{"name": "Component 1", "role": "HBD", "function": "Primary hydrogen bond donor"}},
            {{"name": "Component 2", "role": "HBA", "function": "Hydrogen bond acceptor"}},
            {{"name": "Component 3", "role": "HBD/modifier", "function": "Secondary donor to tune properties"}}
        ],
        "molar_ratio": "1:2:0.5",
        "num_components": {num_components}
    }},
    "reasoning": "...",
    "confidence": 0.0,
    "supporting_evidence": ["...", "..."],
    "synergy_explanation": "Component X and Y synergistically..."
}}
```

**Key Design Considerations for Multi-Component DES**:
- **Ternary DES (3 components)**: Often used to tune viscosity, melting point, or solubility
- **Quaternary DES (4+ components)**: Can provide fine-tuned properties but increase complexity
- **Synergy**: Multiple HBDs or HBAs can create cooperative effects
- **Literature precedent**: Check if similar multi-component systems have been reported
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
                - solubility: Measured solubility value
                - solubility_unit: Unit of solubility
                - is_liquid_formed: Whether DES liquid formed
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
            >>> print(f"Solubility: {result['solubility']} {result['solubility_unit']}")
            >>> print(f"Extracted {len(result['memories_extracted'])} new memories")
        """
        logger.info(f"Processing experimental feedback for recommendation {recommendation_id}")

        try:
            # Check if this is an update (recommendation already has feedback)
            existing_rec = self.rec_manager.get_recommendation(recommendation_id)
            is_update = (
                existing_rec is not None and
                existing_rec.experiment_result is not None and
                existing_rec.trajectory.metadata.get("feedback_processed_at") is not None
            )

            if is_update:
                logger.info(f"Detected feedback update for {recommendation_id}")

            # Step 1: Submit experimental feedback to recommendation manager
            self.rec_manager.submit_feedback(recommendation_id, experiment_result)

            # Step 2: Use FeedbackProcessor to extract memories and update ReasoningBank
            process_result = self.feedback_processor.process_feedback(
                recommendation_id,
                is_update=is_update
            )

            # Log using raw solubility instead of performance_score
            solubility_str = (
                f"{process_result['solubility']} {process_result['solubility_unit']}"
                if process_result.get('solubility') is not None
                else "N/A"
            )
            logger.info(
                f"Feedback processing completed: {process_result['num_memories']} "
                f"memories extracted (solubility: {solubility_str})"
            )

            # Auto-save if configured
            if self.config.get("memory", {}).get("auto_save", False):
                save_path = self.config["memory"]["persist_path"]
                self.memory.save(save_path)
                logger.info(f"Auto-saved memory bank to {save_path}")

            # Build message using raw solubility
            solubility_str = (
                f"{process_result['solubility']} {process_result['solubility_unit']}"
                if process_result.get('solubility') is not None
                else "N/A (DES not formed)"
            )

            message = f"Experimental feedback processed successfully. Solubility: {solubility_str}. "
            if is_update:
                deleted = process_result.get("deleted_memories", 0)
                message += f"Updated feedback (deleted {deleted} old memories). "
            message += f"Extracted {process_result['num_memories']} new memories."

            return {
                "status": "success",
                "recommendation_id": recommendation_id,
                "solubility": process_result.get("solubility"),
                "solubility_unit": process_result.get("solubility_unit"),
                "is_liquid_formed": process_result.get("is_liquid_formed"),
                "memories_extracted": process_result["memories_extracted"],
                "is_update": is_update,
                "deleted_memories": process_result.get("deleted_memories", 0) if is_update else None,
                "message": message
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
