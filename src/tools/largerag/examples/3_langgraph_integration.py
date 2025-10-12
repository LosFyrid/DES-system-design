"""
LargeRAG + LangGraph 集成示例

演示如何在 LangGraph Agent 中使用 LargeRAG 工具

运行方式：
    python examples/3_langgraph_integration.py
"""

import sys
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from largerag.agent_tool import create_largerag_tool
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent


def example_basic_usage():
    """示例 1：基础用法"""
    print("=" * 70)
    print("  Example 1: Basic LangGraph Integration")
    print("=" * 70)

    # 1. 创建 LargeRAG 工具（一行代码）
    largerag_tool = create_largerag_tool()

    # 2. 创建 LangGraph ReAct Agent
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
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
    llm = ChatOpenAI(model="gpt-4o-mini")
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

    from largerag.agent_tool import LargeRAGTool

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
        print("    from largerag import LargeRAG")
        print("    rag = LargeRAG()")
        print("    rag.index_from_folders('data/literature')")
    else:
        print("\n✓ Tool is ready to use!")

    print("\n✓ Example completed\n")


def example_custom_parameters():
    """示例 4：自定义参数"""
    print("=" * 70)
    print("  Example 4: Custom Retrieval Parameters")
    print("=" * 70)

    from largerag.agent_tool import LargeRAGTool

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
