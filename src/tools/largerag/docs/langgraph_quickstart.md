# LargeRAG + LangGraph 快速开始指南

本指南帮助你在 5 分钟内将 LargeRAG 集成到 LangGraph Agent。

---

## 快速开始（3 步）

### 1. 确保索引已构建

```python
from largerag import LargeRAG

# 首次运行：构建索引
rag = LargeRAG()
rag.index_from_folders("src/tools/largerag/data/literature")
```

> 💡 **提示**: 索引构建完成后会持久化，后续无需重复构建。

### 2. 创建 LangGraph Agent

```python
from largerag import create_largerag_tool
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent
import os

# 一行创建工具
tool = create_largerag_tool()

# 创建 DashScope LLM（OpenAI 兼容接口）
llm = ChatOpenAI(
    model="qwen-turbo",
    openai_api_key=os.getenv("DASHSCOPE_API_KEY"),
    openai_api_base="https://dashscope.aliyuncs.com/compatible-mode/v1"
)

# 创建 Agent
agent = create_react_agent(llm, tools=[tool])
```

### 3. 使用 Agent

```python
# 执行查询
result = agent.invoke({
    "messages": [{
        "role": "user",
        "content": "What are the main properties of deep eutectic solvents?"
    }]
})

# 获取回答
print(result["messages"][-1].content)
```

**完成！** 🎉

---

## 完整示例

```python
"""
LargeRAG + LangGraph 完整示例
"""

from largerag import create_largerag_tool
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent

# 创建工具
largerag_tool = create_largerag_tool()

# 创建 Agent（可以添加更多工具）
llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
agent = create_react_agent(
    model=llm,
    tools=[largerag_tool]  # 可以添加更多工具：[largerag_tool, corerag_tool, ...]
)

# 执行查询
query = "What are typical DES viscosity values at low temperature?"

result = agent.invoke({
    "messages": [{"role": "user", "content": query}]
})

print(result["messages"][-1].content)
```

---

## 流式输出（实时查看推理过程）

```python
# 使用 stream 代替 invoke
for chunk in agent.stream({"messages": [{"role": "user", "content": query}]}):
    # 打印 Agent 的推理步骤
    if "agent" in chunk:
        print(f"[Agent] {chunk['agent']['messages'][0].content}")
    elif "tools" in chunk:
        print(f"[Tool] {chunk['tools']['messages'][0].content[:100]}...")
```

**输出示例**：
```
[Agent] I need to search for DES viscosity information...
[Tool] Retrieved 5 documents:
[1] Score: 0.892 | Content: Deep eutectic solvents exhibit...
[Agent] Based on the retrieved literature, DES viscosity at low temperature...
```

---

## 多工具 Agent

LargeRAG 可以与其他工具组合使用：

```python
from langchain_core.tools import tool

# 定义其他工具
@tool
def calculate_molar_ratio(hba: float, hbd: float) -> str:
    """Calculate molar ratio between HBA and HBD."""
    return f"Molar ratio: {hba/hbd:.2f}:1"

# 创建多工具 Agent
agent = create_react_agent(
    llm,
    tools=[
        create_largerag_tool(),  # LargeRAG
        calculate_molar_ratio     # 自定义工具
    ]
)

# Agent 会根据需���选择合适的工具
result = agent.invoke({
    "messages": [{
        "role": "user",
        "content": "What is the typical ChCl:Urea ratio in DES?"
    }]
})
```

---

## 检查工具状态

```python
from largerag import LargeRAGTool

# 创建工具实例
tool_instance = LargeRAGTool()

# 检查索引状态
stats = tool_instance.rag.get_stats()

print(f"Index Ready: {tool_instance.rag.query_engine is not None}")
print(f"Index Nodes: {stats['index_stats'].get('document_count', 0)}")
print(f"Collection: {stats['index_stats'].get('collection_name')}")
```

**输出示例**：
```
Index Ready: True
Index Nodes: 1234
Collection: des_literature_v1
```

---

## 自定义参数（直接调用）

如果需要更精细的控制，可以直接调用 `retrieve` 方法：

```python
from largerag import LargeRAGTool

tool = LargeRAGTool()

# 自定义参数
result = tool.retrieve(
    query="DES viscosity",
    top_k=10,           # 返回 10 个文档（默认 5）
    min_score=0.7       # 只返回分数 >= 0.7 的文档
)

print(result)
```

---

## 配置 API Key

**本项目默认使用 DashScope**，只需要一个 API Key：

### 方式 1：环境变量（推荐）

```bash
# .env 文件（只需要这一个）
DASHSCOPE_API_KEY=your_api_key_here
```

### 方式 2：代码中设置

```python
import os
os.environ["DASHSCOPE_API_KEY"] = "your_api_key_here"
```

**说明**：
- LargeRAG 工具：使用 DashScope 原生 API（Embedding + Reranker）
- LangGraph Agent：使用 DashScope OpenAI 兼容接口（LLM）
- 两者共用同一个 `DASHSCOPE_API_KEY`，无需额外配置

---

## 常见问题

### Q1: 报错 "Index not initialized"

**原因**: 索引尚未构建

**解决**:
```python
from largerag import LargeRAG
rag = LargeRAG()
rag.index_from_folders("src/tools/largerag/data/literature")
```

### Q2: 如何更改返回文档数量？

**方式 1**: 在 Agent 工具中（Agent 会自动调用）
```python
# Agent 会根据需要自动设置 top_k
agent.invoke({...})
```

**方式 2**: 直接调用（绕过 Agent）
```python
tool = LargeRAGTool()
result = tool.retrieve("query", top_k=10)
```

### Q3: 如何查看 Agent 调用了哪些工具？

```python
result = agent.invoke({...})

# 提取工具调用记录
for msg in result["messages"]:
    if hasattr(msg, "name"):  # 工具调用消息
        print(f"Tool called: {msg.name}")
```

### Q4: 检索结果不相关怎么办？

**方法 1**: 提高分数阈值
```python
tool.retrieve(query, min_score=0.7)  # 只返回高质量结果
```

**方法 2**: 优化查询描述
```python
# ❌ 不好的查询
"DES"

# ✅ 好的查询
"What are the viscosity properties of deep eutectic solvents at low temperature?"
```

---

## 进阶用法

### 自定义工具描述

```python
from largerag import LargeRAGTool

tool = LargeRAGTool()

# 修改工具描述（需要修改 agent_tool.py 中的 docstring）
# 参考 docs/extension_guide.md 场景 4
```

### 添加统计追踪

参考 `docs/extension_guide.md` 场景 1

### 支持多种输出格式

参考 `docs/extension_guide.md` 场景 2

---

## 完整示例代码

查看 `examples/3_langgraph_integration.py` 了解更多使用示例：

```bash
# 运行示例
python examples/3_langgraph_integration.py --example 1
```

**4 个示例**：
1. 基础用法
2. 多轮对话
3. 工具状态检查
4. 自定义参数

---

## 下一步

- 📖 阅读 [扩展指南](./extension_guide.md) 了解如何自定义工具
- 🔧 查看 [agent_tool.py](../agent_tool.py) 了解实现细节
- 🚀 运行 [完整示例](../examples/3_langgraph_integration.py) 体验功能

---

## 总结

**最简用法（3 行）**：
```python
from largerag import create_largerag_tool
tool = create_largerag_tool()
agent = create_react_agent(llm, tools=[tool])
```

**就这么简单！** 🎉
