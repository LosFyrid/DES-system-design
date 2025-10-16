"""
Example: Async Experimental Feedback Loop

This example demonstrates the complete async feedback workflow using REAL LLM:
1. Agent generates DES formulation recommendation
2. User performs experiment (simulated delay)
3. User submits experimental results
4. System extracts data-driven memories and learns (using real LLM)
5. Cross-instance data reuse

Run this script to see the async feedback system in action with actual LLM calls.

Requirements:
- DASHSCOPE_API_KEY in .env file (or OPENAI_API_KEY for OpenAI)
- Configuration is loaded from src/agent/config/reasoningbank_config.yaml
"""

import sys
from pathlib import Path
import logging
import time
from dotenv import load_dotenv

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from agent.reasoningbank import (
    ReasoningBank,
    MemoryRetriever,
    MemoryExtractor,
    LLMJudge,
    ExperimentResult,
    RecommendationManager
)
from agent.des_agent import DESAgent
from agent.utils.llm_client import LLMClient
from agent.utils.embedding_client import EmbeddingClient
from agent.config import get_config

# Load environment variables from .env
load_dotenv()

# Load configuration from YAML
config = get_config()

# Configure logging from config
log_config = config.get_logging_config()
logging.basicConfig(
    level=getattr(logging, log_config.get("level", "INFO")),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def create_llm_client_from_config(llm_type: str = "llm") -> LLMClient:
    """
    Create LLM client from configuration file.

    Args:
        llm_type: "llm" (default components) or "agent_llm" (main reasoning)

    Returns:
        Configured LLMClient instance
    """
    llm_config = config.get_llm_config(llm_type)

    return LLMClient(
        provider=llm_config["provider"],
        model=llm_config["model"],
        temperature=llm_config["temperature"],
        max_tokens=llm_config["max_tokens"],
        base_url=llm_config.get("api_base")  # None for default providers
    )


def main():
    """
    Demonstrate complete async feedback workflow with REAL LLM.
    All parameters loaded from configuration file.
    """
    print("="*80)
    print("ASYNC EXPERIMENTAL FEEDBACK WORKFLOW DEMONSTRATION")
    print("="*80)
    print()

    # ===== Setup Phase =====
    print("Phase 1: System Initialization (from config)")
    print("-" * 80)

    # Initialize LLM clients from config
    try:
        # Default LLM for retriever, judge, etc.
        llm_client = create_llm_client_from_config("llm")
        llm_config = config.get_llm_config("llm")
        print(f"✓ LLM Client initialized: {llm_config['provider']} ({llm_config['model']})")

        # Agent LLM for main reasoning (may be different model)
        agent_llm_client = create_llm_client_from_config("agent_llm")
        agent_llm_config = config.get_llm_config("agent_llm")
        print(f"✓ Agent LLM Client initialized: {agent_llm_config['provider']} ({agent_llm_config['model']})")

        # Embedding client from config
        embedding_config = config.get_embedding_config()
        embedding_client = EmbeddingClient(
            provider=embedding_config["provider"],
            model=embedding_config["model"],
            dimension=embedding_config.get("dimension")
        )
        print(f"✓ Embedding Client initialized: {embedding_config['provider']} ({embedding_config['model']})")

    except Exception as e:
        logger.error(f"Failed to initialize clients: {e}")
        print("\n❌ Error: Could not initialize LLM/Embedding client")
        print("   Please check your API key in .env file")
        return

    # Get paths from config
    memory_config = config.get_memory_config()
    rec_config = config.get_recommendations_config()

    # For demo: use demo_outputs instead of config paths
    demo_dir = Path(__file__).parent / "demo_outputs"
    recommendations_dir = demo_dir / "recommendations"
    memory_dir = demo_dir / "memory"

    recommendations_dir.mkdir(parents=True, exist_ok=True)
    memory_dir.mkdir(parents=True, exist_ok=True)

    # Initialize extractor with config temperature
    extractor_config = config.get_extractor_config()
    extractor_temp = extractor_config.get("temperature", 1.0)

    # Initialize ReasoningBank components from config
    memory_bank = ReasoningBank()
    retriever = MemoryRetriever(
        bank=memory_bank,
        embedding_func=embedding_client.embed  # Use embedding client's embed method
    )
    extractor = MemoryExtractor(llm_client, temperature=extractor_temp)
    judge = LLMJudge(llm_client)  # Not used in v1, but required
    rec_manager = RecommendationManager(storage_path=str(recommendations_dir))

    # Initialize DESAgent with config
    agent = DESAgent(
        llm_client=agent_llm_client,  # Use agent_llm for main reasoning
        reasoning_bank=memory_bank,
        retriever=retriever,
        extractor=extractor,
        judge=judge,
        rec_manager=rec_manager,
        config={
            "memory": {
                "auto_save": memory_config.get("auto_save", True),
                "persist_path": str(memory_dir / "reasoning_bank.json")
            }
        }
    )

    print(f"✓ Initialized DESAgent with async feedback support")
    print(f"✓ Extractor temperature: {extractor_temp} (from config)")
    print(f"✓ Recommendations storage: {recommendations_dir}")
    print(f"✓ Memory storage: {memory_dir}")
    print(f"✓ Memory auto-save: {memory_config.get('auto_save')}")
    print()

    # ===== Task Submission Phase =====
    print("Phase 2: Task Submission & Recommendation Generation")
    print("-" * 80)

    task = {
        "task_id": "demo_task_001",
        "description": "Design a DES formulation to dissolve cellulose at room temperature (25°C)",
        "target_material": "cellulose",
        "target_temperature": 25,
        "constraints": {
            "max_viscosity": "100 cP",
            "component_availability": "common chemicals only"
        }
    }

    print(f"Task: {task['description']}")
    print(f"Target Material: {task['target_material']}")
    print(f"Target Temperature: {task['target_temperature']}°C")
    print()

    # Generate recommendation
    print("⏳ Generating formulation recommendation (calling LLM)...")
    result = agent.solve_task(task)

    print(f"✓ Recommendation Generated: {result['recommendation_id']}")
    print(f"  Status: {result['status']}")
    print(f"  Formulation: {result['formulation']}")
    print(f"  Reasoning: {result['reasoning'][:150]}...")
    print(f"  Confidence: {result.get('confidence', 'N/A')}")
    print()
    print(f"Next Step: {result['next_steps']}")
    print()

    recommendation_id = result['recommendation_id']

    # ===== Simulated Experiment Phase =====
    print("Phase 3: Experimental Testing (Simulated)")
    print("-" * 80)
    print("⏳ User performs laboratory experiment...")
    print("   - Preparing components based on recommendation")
    print("   - Mixing components at target temperature")
    print("   - Testing target material dissolution")
    print("   - Measuring solubility and properties")
    print()

    # Simulate experiment delay (in reality, this could be hours or days)
    time.sleep(2)

    print("✓ Experiment completed!")
    print()

    # ===== Feedback Submission Phase =====
    print("Phase 4: Experimental Feedback Submission")
    print("-" * 80)

    # Create experimental result
    experiment_result = ExperimentResult(
        is_liquid_formed=True,
        solubility=6.5,
        solubility_unit="g/L",
        properties={
            "viscosity": "45 cP",
            "appearance": "clear liquid",
            "color": "colorless"
        },
        notes="DES formed successfully at room temperature. Clear homogeneous liquid observed. Cellulose dissolution was moderate but consistent."
    )

    print(f"Experimental Results:")
    print(f"  - DES Formation: {'✓ Yes' if experiment_result.is_liquid_formed else '✗ No'}")
    print(f"  - Solubility: {experiment_result.solubility} {experiment_result.solubility_unit}")
    print(f"  - Performance Score: {experiment_result.get_performance_score():.1f}/10.0")
    print(f"  - Viscosity: {experiment_result.properties['viscosity']}")
    print(f"  - Notes: {experiment_result.notes[:80]}...")
    print()

    # Submit feedback to agent
    print("⏳ Processing experimental feedback (calling LLM for memory extraction)...")
    feedback_result = agent.submit_experiment_feedback(recommendation_id, experiment_result)

    print(f"✓ Feedback Processed: {feedback_result['status'].upper()}")
    print(f"  - Recommendation: {feedback_result['recommendation_id']}")
    print(f"  - Performance: {feedback_result['performance_score']:.1f}/10.0")
    print(f"  - Memories Extracted: {len(feedback_result['memories_extracted'])}")
    for i, mem_title in enumerate(feedback_result['memories_extracted'], 1):
        print(f"    {i}. {mem_title}")
    print()

    # ===== Query Recommendations Phase =====
    print("Phase 5: Query Recommendations")
    print("-" * 80)

    # List all recommendations
    all_recs = rec_manager.list_recommendations()
    print(f"Total recommendations in system: {len(all_recs)}")

    # List completed recommendations
    completed_recs = rec_manager.list_recommendations(status="COMPLETED")
    print(f"Completed recommendations: {len(completed_recs)}")

    # List by target material
    cellulose_recs = rec_manager.list_recommendations(target_material="cellulose")
    print(f"Recommendations for cellulose: {len(cellulose_recs)}")
    print()

    # ===== Cross-Instance Data Reuse Phase =====
    print("Phase 6: Cross-Instance Data Reuse (Simulated)")
    print("-" * 80)
    print("Scenario: System B wants to learn from System A's experimental data")
    print()

    # Create a new agent instance (System B) - also using config
    memory_bank_B = ReasoningBank()
    retriever_B = MemoryRetriever(
        bank=memory_bank_B,
        embedding_func=embedding_client.embed
    )
    extractor_B = MemoryExtractor(llm_client, temperature=extractor_temp)
    judge_B = LLMJudge(llm_client)
    rec_manager_B = RecommendationManager(storage_path=str(demo_dir / "system_B_recs"))

    agent_B = DESAgent(
        llm_client=agent_llm_client,
        reasoning_bank=memory_bank_B,
        retriever=retriever_B,
        extractor=extractor_B,
        judge=judge_B,
        rec_manager=rec_manager_B,
        config={}
    )

    print("✓ System B initialized with empty memory bank")
    print(f"  Current memories in System B: {len(agent_B.memory.memories)}")
    print()

    # Load System A's data into System B
    print(f"Loading System A's data from: {recommendations_dir}")
    print("⏳ Reprocessing with System B's extraction logic (calling LLM)...")
    load_result = agent_B.load_historical_recommendations(
        data_path=str(recommendations_dir),
        reprocess=True  # Re-extract with System B's logic
    )

    print(f"✓ Historical Data Loaded: {load_result['status'].upper()}")
    print(f"  - Recommendations loaded: {load_result['num_loaded']}")
    print(f"  - Reprocessed with new logic: {load_result['num_reprocessed']}")
    print(f"  - Memories added to System B: {load_result['memories_added']}")
    print(f"  Current memories in System B: {len(agent_B.memory.memories)}")
    print()

    # ===== Summary =====
    print("="*80)
    print("WORKFLOW COMPLETE")
    print("="*80)
    print()
    print("Summary:")
    print(f"  1. Generated recommendation: {recommendation_id}")
    print(f"  2. Simulated laboratory experiment")
    print(f"  3. Submitted feedback with performance score: {experiment_result.get_performance_score():.1f}/10.0")
    print(f"  4. Extracted {len(feedback_result['memories_extracted'])} data-driven memories")
    print(f"  5. Demonstrated cross-instance data reuse (System A → System B)")
    print()
    print("Key Features Demonstrated:")
    print("  ✓ Asynchronous workflow (recommendation → experiment → feedback)")
    print("  ✓ Real experimental measurements (not binary success/failure)")
    print("  ✓ Data-driven memory extraction (quantitative relationships)")
    print("  ✓ Persistent storage (JSON-based recommendation tracking)")
    print("  ✓ Cross-instance reusability (System A data → System B learning)")
    print("  ✓ Configuration-driven setup (all params from reasoningbank_config.yaml)")
    print()
    print(f"Configuration used:")
    print(f"  - LLM: {llm_config['provider']}/{llm_config['model']}")
    print(f"  - Agent LLM: {agent_llm_config['provider']}/{agent_llm_config['model']}")
    print(f"  - Extractor temperature: {extractor_temp}")
    print(f"  - Memory auto-save: {memory_config.get('auto_save')}")
    print()
    print(f"Output files saved to: {demo_dir}")
    print()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logger.error(f"Demo failed with error: {e}", exc_info=True)
        sys.exit(1)
