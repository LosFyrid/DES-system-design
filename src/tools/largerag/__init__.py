"""
LargeRAG - Large-scale Literature Retrieval Tool

A LlamaIndex-based RAG system for retrieving information from ~10,000 DES literature papers.

Usage:
    # Basic RAG usage
    from largerag import LargeRAG
    rag = LargeRAG()
    rag.index_from_folders("data/literature")
    answer = rag.query("What are DES?")

    # LangGraph Agent integration
    from largerag import create_largerag_tool
    tool = create_largerag_tool()
    agent = create_react_agent(llm, tools=[tool])
"""

from .largerag import LargeRAG
from .agent_tool import create_largerag_tool, LargeRAGTool

__version__ = "1.0.0"
__all__ = ["LargeRAG", "create_largerag_tool", "LargeRAGTool"]
