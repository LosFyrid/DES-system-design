"""
LargeRAG + LangGraph 集成示例

演示如何在 LangGraph Agent 中使用 LargeRAG 工具

运行方式：
    python examples/3_langgraph_integration.py

环境要求：
    .env 文件需包含：
    - DASHSCOPE_API_KEY: DashScope API Key（用于 LargeRAG 和 LLM）
"""

import sys
import os
from pathlib import Path

# 添加项目根目录到路径（向上 5 级：examples -> largerag -> tools -> src -> 项目根）
project_root = Path(__file__).resolve().parent.parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent

from src.tools.largerag.agent_tool import create_largerag_tool


# ============================================================
# DashScope LLM 配置（项目默认）
# ============================================================

def create_dashscope_llm(model: str = "qwen3-235b-a22b-thinking-2507", temperature: float = 0):
    """
    创建 DashScope LLM（通过 OpenAI 兼容接口）

    Args:
        model: 模型名称（qwen-turbo, qwen-plus, qwen-max）
        temperature: 温度参数

    Returns:
        ChatOpenAI: 配置好的 LLM 实例
    """
    api_key = os.getenv("DASHSCOPE_API_KEY")
    if not api_key:
        raise ValueError(
            "DASHSCOPE_API_KEY not found in environment variables. "
            "Please add it to .env file."
        )

    return ChatOpenAI(
        model=model,
        temperature=temperature,
        openai_api_key=api_key,
        openai_api_base="https://dashscope.aliyuncs.com/compatible-mode/v1"
    )


def example_basic_usage():
    """示例 1：基础用法"""
    print("=" * 70)
    print("  Example 1: Basic LangGraph Integration")
    print("=" * 70)

    # 1. 创建 LargeRAG 工具（一行代码）
    largerag_tool = create_largerag_tool()

    # 2. 创建 DashScope LLM
    llm = create_dashscope_llm(model="qwen-turbo", temperature=0)

    # 3. 创建 LangGraph ReAct Agent
    agent = create_react_agent(
        model=llm,
        tools=[largerag_tool]
    )

    # 3. 执行查询
    query = "What are the main properties of deep eutectic solvents?"

    print(f"\nUser Query: {query}\n")
    print("Agent Reasoning...\n")

    # 流式输出（实时看到 Agent 推理过程）
    for chunk in agent.stream({"messages": [{"role": "user", "content": query}]}):
        if "agent" in chunk:
            print(f"[Agent] {chunk['agent']['messages'][0].content}")
        elif "tools" in chunk:
            print(f"[Tool] {chunk['tools']['messages'][0].content[:200]}...")
        print("-" * 70)

    print("\n✓ Example completed\n")


def example_multi_turn_conversation():
    """示例 2：多轮对话"""
    print("=" * 70)
    print("  Example 2: Multi-Turn Conversation")
    print("=" * 70)

    tool = create_largerag_tool()
    llm = create_dashscope_llm(model="qwen-turbo")
    agent = create_react_agent(llm, tools=[tool])

    # 模拟多轮对话
    conversation = [
        "What are deep eutectic solvents?",
        "What are typical applications of DES in chemistry?",
        "How does temperature affect DES viscosity?"
    ]

    messages = []

    for i, user_input in enumerate(conversation, 1):
        print(f"\n[Turn {i}] User: {user_input}")

        messages.append({"role": "user", "content": user_input})

        result = agent.invoke({"messages": messages})

        # 提取最后的回答
        assistant_response = result["messages"][-1].content
        messages.append({"role": "assistant", "content": assistant_response})

        print(f"[Turn {i}] Agent: {assistant_response[:200]}...\n")

    print("\n✓ Example completed\n")


def example_check_tool_status():
    """示例 3：检查工具状态"""
    print("=" * 70)
    print("  Example 3: Check Tool Status")
    print("=" * 70)

    from src.tools.largerag.agent_tool import LargeRAGTool

    # 直接创建工具实例（可以访问更多方法）
    tool = LargeRAGTool()

    # 检查索引状态
    stats = tool.rag.get_stats()

    print("\nLargeRAG Tool Status:")
    print(f"  Index Ready: {tool.rag.query_engine is not None}")
    print(f"  Index Nodes: {stats['index_stats'].get('document_count', 0)}")
    print(f"  Collection: {stats['index_stats'].get('collection_name', 'N/A')}")
    print(f"  Processed Docs: {stats['doc_processing_stats'].get('processed', 0)}")

    if not tool.rag.query_engine:
        print("\n⚠️  Index not ready. Please build it first:")
        print("    from src.tools.largerag import LargeRAG")
        print("    rag = LargeRAG()")
        print("    rag.index_from_folders('src/tools/largerag/data/literature')")
    else:
        print("\n✓ Tool is ready to use!")

    print("\n✓ Example completed\n")


def example_custom_parameters():
    """示例 4：自定义参数"""
    print("=" * 70)
    print("  Example 4: Custom Retrieval Parameters")
    print("=" * 70)

    from src.tools.largerag.agent_tool import LargeRAGTool

    tool = LargeRAGTool()

    # 直接调用 retrieve 方法（不通过 Agent）
    query = "DES viscosity at low temperature"

    print(f"Query: {query}\n")
    print("Testing different parameters:\n")

    # 测试 1：默认参数
    print("[Test 1] Default (top_k=5, min_score=0.0)")
    result1 = tool.retrieve(query)
    print(result1[:300] + "...\n")

    # 测试 2：高阈值
    print("[Test 2] High threshold (top_k=3, min_score=0.7)")
    result2 = tool.retrieve(query, top_k=3, min_score=0.7)
    print(result2[:300] + "...\n")

    print("\n✓ Example completed\n")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="LargeRAG + LangGraph Integration Examples"
    )
    parser.add_argument(
        "--example",
        type=int,
        choices=[1, 2, 3, 4],
        help="Which example to run (1-4, default: 1)"
    )

    args = parser.parse_args()

    try:
        if args.example == 1 or args.example is None:
            example_basic_usage()
        elif args.example == 2:
            example_multi_turn_conversation()
        elif args.example == 3:
            example_check_tool_status()
        elif args.example == 4:
            example_custom_parameters()

    except KeyboardInterrupt:
        print("\n\n⚠️  Example interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
