# LargeRAG 工具扩展指南

**版本**: 1.0
**适用于**: `agent_tool.py` 精简版

---

## 概述

本文档说明如何扩展 `agent_tool.py` 的功能。精简版设计遵循"最小化核心，按需扩展"原则，所有扩展点都已在代码中预留清晰标注。

---

## 核心架构

```
LargeRAGTool
├── __init__()           # 初始化 LargeRAG
├── retrieve()           # 核心检索逻辑 ⭐ 主要扩展点
├── _format_results()    # 格式化输出 ⭐ 主要扩展点
└── as_tool()            # 转换为 LangChain Tool

create_largerag_tool()   # 便捷创建函数 ⭐ 扩展点
```

---

## 扩展场景与实现

### 场景 1：添加统计追踪

**需求**: 追踪工具调用次数、检索文档数等统计信息

**实现方式**:

```python
class LargeRAGTool:
    def __init__(self):
        self.rag = LargeRAG()

        # 添加统计字典
        self._stats = {
            "call_count": 0,
            "total_docs_retrieved": 0,
            "total_queries": 0
        }

    def retrieve(self, query: str, top_k: int = 5, min_score: float = 0.0) -> str:
        # 更新统计
        self._stats["call_count"] += 1
        self._stats["total_queries"] += 1

        # ... 原有检索逻辑 ...
        docs = self.rag.get_similar_docs(query, top_k=top_k)

        # 更新统计
        self._stats["total_docs_retrieved"] += len(docs)

        # ... 后续逻辑 ...

    def get_stats(self) -> dict:
        """新增方法：获取统计信息"""
        return {
            **self._stats,
            "avg_docs_per_call": (
                self._stats["total_docs_retrieved"] / self._stats["call_count"]
                if self._stats["call_count"] > 0 else 0
            )
        }
```

**使用示例**:
```python
tool = LargeRAGTool()
tool.retrieve("DES properties")
print(tool.get_stats())
# Output: {"call_count": 1, "total_docs_retrieved": 5, ...}
```

---

### 场景 2：支持多种输出格式

**需求**: 支持 JSON、Markdown、纯文本等多种输出格式

**实现方式**:

```python
class LargeRAGTool:
    def __init__(self, format_style: str = "default"):
        """
        Args:
            format_style: 'default', 'json', 'markdown', 'compact'
        """
        self.rag = LargeRAG()
        self.format_style = format_style

    def _format_results(self, query: str, docs: list) -> str:
        """根据 format_style 选择格式化方式"""
        if self.format_style == "json":
            return self._format_json(docs)
        elif self.format_style == "markdown":
            return self._format_markdown(docs)
        elif self.format_style == "compact":
            return self._format_compact(docs)
        else:
            return self._format_default(query, docs)

    def _format_default(self, query: str, docs: list) -> str:
        """默认格式（保持原有逻辑）"""
        # ... 原有代码 ...

    def _format_json(self, docs: list) -> str:
        """JSON 格式"""
        import json
        return json.dumps([{
            "text": doc["text"],
            "score": doc["score"],
            "source": doc["metadata"]["doc_hash"][:8]
        } for doc in docs], indent=2)

    def _format_markdown(self, docs: list) -> str:
        """Markdown 格式"""
        result = ["# Retrieval Results\n"]
        for i, doc in enumerate(docs, 1):
            result.append(f"## Document {i} (Score: {doc['score']:.3f})")
            result.append(f"**Source**: {doc['metadata']['doc_hash'][:8]}...\n")
            result.append(doc['text'][:300] + "...\n")
        return "\n".join(result)

    def _format_compact(self, docs: list) -> str:
        """紧凑格式（只返回文本，无元数据）"""
        return "\n\n".join([doc["text"][:200] for doc in docs])
```

**便捷函数扩展**:
```python
def create_largerag_tool(format_style: str = "default"):
    """支持格式参数"""
    return LargeRAGTool(format_style=format_style).as_tool()
```

**使用示例**:
```python
# JSON 格式
tool_json = create_largerag_tool(format_style="json")

# Markdown 格式
tool_md = create_largerag_tool(format_style="markdown")
```

---

### 场景 3：添加结果缓存

**需求**: 缓存检索结果，避免重复查询

**实现方式**:

```python
from functools import lru_cache
import hashlib

class LargeRAGTool:
    def __init__(self, enable_cache: bool = True):
        self.rag = LargeRAG()
        self.enable_cache = enable_cache

    def retrieve(self, query: str, top_k: int = 5, min_score: float = 0.0) -> str:
        if self.enable_cache:
            return self._retrieve_cached(query, top_k, min_score)
        else:
            return self._retrieve_impl(query, top_k, min_score)

    @lru_cache(maxsize=100)
    def _retrieve_cached(self, query: str, top_k: int, min_score: float) -> str:
        """带缓存的检索"""
        return self._retrieve_impl(query, top_k, min_score)

    def _retrieve_impl(self, query: str, top_k: int, min_score: float) -> str:
        """实际检索逻辑（原 retrieve 方法内容）"""
        # ... 原有检索代码 ...
        pass

    def clear_cache(self):
        """清空缓存"""
        if hasattr(self, '_retrieve_cached'):
            self._retrieve_cached.cache_clear()
```

**使用示例**:
```python
tool = LargeRAGTool(enable_cache=True)
tool.retrieve("DES properties")  # 从数据库检索
tool.retrieve("DES properties")  # 从缓存返回（快速）
tool.clear_cache()  # 清空缓存
```

---

### 场景 4：自定义工具名称和描述

**需求**: 为不同场景定制工具名称和描述

**实现方式**:

```python
class LargeRAGTool:
    def __init__(self, tool_name: str = "retrieve_des_literature",
                 tool_description: str = None):
        self.rag = LargeRAG()
        self.tool_name = tool_name
        self.tool_description = tool_description

    def as_tool(self):
        """使用自定义名称和描述"""
        retrieve_func = self.retrieve
        tool_name = self.tool_name
        tool_desc = self.tool_description or self._default_description()

        @tool
        def custom_tool(query: str, top_k: int = 5) -> str:
            # 动态设置 docstring
            custom_tool.__doc__ = tool_desc
            return retrieve_func(query, top_k)

        # 修改函数名
        custom_tool.__name__ = tool_name

        return custom_tool

    def _default_description(self) -> str:
        return """
        Retrieve background knowledge about Deep Eutectic Solvents (DES)...
        """
```

**便捷函数扩展**:
```python
def create_largerag_tool(tool_name: str = "retrieve_des_literature",
                         tool_description: str = None):
    return LargeRAGTool(
        tool_name=tool_name,
        tool_description=tool_description
    ).as_tool()
```

**使用示例**:
```python
# 自定义工具
tool = create_largerag_tool(
    tool_name="search_des_papers",
    tool_description="Search DES literature with focus on viscosity data"
)
```

---

### 场景 5：添加配置系统

**需求**: 支持通过配置字典自定义多个参数

**实现方式**:

```python
class LargeRAGTool:
    def __init__(self, config: dict = None):
        """
        Args:
            config: 配置字典，支持的键：
                - default_top_k: 默认返回文档数（默认 5）
                - default_min_score: 默认最低分数（默认 0.0）
                - max_text_length: 文本截断长度（默认 300）
                - enable_cache: 是否启用缓存（默认 False）
                - format_style: 输出格式（默认 'default'）
        """
        self.rag = LargeRAG()
        self.config = config or {}

        # 解析配置
        self.default_top_k = self.config.get("default_top_k", 5)
        self.default_min_score = self.config.get("default_min_score", 0.0)
        self.max_text_length = self.config.get("max_text_length", 300)
        self.enable_cache = self.config.get("enable_cache", False)
        self.format_style = self.config.get("format_style", "default")

    def retrieve(self, query: str, top_k: int = None, min_score: float = None) -> str:
        # 使用配置的默认值
        top_k = top_k if top_k is not None else self.default_top_k
        min_score = min_score if min_score is not None else self.default_min_score

        # ... 原有逻辑，使用 self.max_text_length 截断文本 ...
```

**便捷函数扩展**:
```python
def create_largerag_tool(config: dict = None):
    return LargeRAGTool(config=config).as_tool()
```

**使用示例**:
```python
# 使用配置创建工具
tool = create_largerag_tool(config={
    "default_top_k": 10,
    "default_min_score": 0.5,
    "max_text_length": 500,
    "enable_cache": True,
    "format_style": "markdown"
})
```

---

### 场景 6：添加日志和调试信息

**需求**: 详细记录检索过程，便于调试

**实现方式**:

```python
import logging
from datetime import datetime

class LargeRAGTool:
    def __init__(self, log_level: str = "INFO"):
        self.rag = LargeRAG()

        # 配置日志
        self.logger = logging.getLogger(f"{__name__}.LargeRAGTool")
        self.logger.setLevel(log_level)

    def retrieve(self, query: str, top_k: int = 5, min_score: float = 0.0) -> str:
        start_time = datetime.now()

        self.logger.info(f"[Retrieve] Query: {query[:100]}...")
        self.logger.debug(f"[Retrieve] Parameters: top_k={top_k}, min_score={min_score}")

        try:
            docs = self.rag.get_similar_docs(query, top_k=top_k)

            self.logger.info(f"[Retrieve] Retrieved {len(docs)} raw documents")

            # 过滤
            filtered_docs = [d for d in docs if d['score'] >= min_score]

            self.logger.info(
                f"[Retrieve] After filtering: {len(filtered_docs)} documents "
                f"(avg score: {sum(d['score'] for d in filtered_docs) / len(filtered_docs):.3f})"
            )

            elapsed = (datetime.now() - start_time).total_seconds()
            self.logger.debug(f"[Retrieve] Completed in {elapsed:.2f}s")

            return self._format_results(query, filtered_docs)

        except Exception as e:
            self.logger.error(f"[Retrieve] Failed: {e}", exc_info=True)
            raise
```

**使用示例**:
```python
# 启用详细日志
logging.basicConfig(level=logging.DEBUG)
tool = LargeRAGTool(log_level="DEBUG")
tool.retrieve("DES properties")
```

---

### 场景 7：与 CoreRAG、Experimental Data 统一接口

**需求**: 多个工具共享统一的基类和接口

**实现方式**:

```python
# src/tools/common/base_tool.py (新建文件)
from abc import ABC, abstractmethod
from langchain_core.tools import tool

class BaseAgentTool(ABC):
    """所有 Agent 工具的基类"""

    @abstractmethod
    def retrieve(self, query: str, **kwargs) -> str:
        """检索方法（子类必须实现）"""
        pass

    @abstractmethod
    def as_tool(self):
        """转换为 LangChain Tool（子类必须实现）"""
        pass

    def check_status(self) -> dict:
        """检查工具状态（可选实现）"""
        return {"status": "unknown"}


# src/tools/largerag/agent_tool.py
from tools.common.base_tool import BaseAgentTool

class LargeRAGTool(BaseAgentTool):
    """继承统一基类"""

    def retrieve(self, query: str, **kwargs) -> str:
        # 实现具体逻辑
        pass

    def as_tool(self):
        # 实现具体逻辑
        pass

    def check_status(self) -> dict:
        stats = self.rag.get_stats()
        return {
            "tool_name": "LargeRAG",
            "status": "ready" if self.rag.query_engine else "not_ready",
            "index_nodes": stats['index_stats'].get('document_count', 0)
        }


# src/tools/corerag/agent_tool.py (未来实现)
class CoreRAGTool(BaseAgentTool):
    """CoreRAG 工具（接口一致）"""
    pass
```

---

## 扩展优先级建议

根据实际需求，推荐按以下顺序扩展：

| 优先级 | 扩展场景 | 复杂度 | 价值 |
|-------|---------|--------|------|
| 🔥 **高** | 场景 6: 日志和调试 | 低 | 高 - 便于问题排查 |
| 🔥 **高** | 场景 1: 统计追踪 | 低 | 高 - 监控工具使用 |
| 🟡 **中** | 场景 2: 多种格式 | 中 | 中 - 看使用场景 |
| 🟡 **中** | 场景 5: 配置系统 | 中 | 中 - 灵活性提升 |
| 🟢 **低** | 场景 3: 结果缓存 | 低 | 中 - 性能优化 |
| 🟢 **低** | 场景 4: 自定义名称 | 低 | 低 - 特殊需求 |
| ⚪ **可选** | 场景 7: 统一基类 | 高 | 中 - 多工具时才需要 |

---

## 扩展最佳实践

### 1. 保持向后兼容

扩展时确保原有代码仍能正常运行：

```python
# ✅ 好的做法：使用可选参数
class LargeRAGTool:
    def __init__(self, enable_cache: bool = False):  # 默认值保持原有行为
        pass

# ❌ 不好的做法：修改现有参数
class LargeRAGTool:
    def __init__(self, cache_config: dict):  # 强制新参数，破坏兼容性
        pass
```

### 2. 渐进式扩展

不要一次性添加所有功能，按需逐步扩展：

```python
# 第一步：添加基础统计
class LargeRAGTool:
    def __init__(self):
        self._call_count = 0  # 只添加一个变量

# 第二步：扩展统计维度
class LargeRAGTool:
    def __init__(self):
        self._stats = {"calls": 0, "docs": 0}  # 扩展为字典

# 第三步：添加统计方法
    def get_stats(self):
        return self._stats
```

### 3. 文档和注释

扩展时更新文档：

```python
class LargeRAGTool:
    """
    LargeRAG 工具封装

    扩展历史：
    - v1.0: 基础功能
    - v1.1: 添加统计追踪
    - v1.2: 添加多格式输出
    """
```

### 4. 测试扩展功能

每次扩展后测试：

```python
# test_agent_tool.py
def test_statistics():
    tool = LargeRAGTool()
    tool.retrieve("test query")
    stats = tool.get_stats()
    assert stats["call_count"] == 1
```

---

## 常见问题

**Q: 扩展后代码变复杂，怎么办？**

A: 考虑创建子类而非修改原类：

```python
# 保持原类简洁
class LargeRAGTool:
    pass

# 扩展功能在子类
class AdvancedLargeRAGTool(LargeRAGTool):
    def __init__(self):
        super().__init__()
        self._stats = {}  # 新增功能
```

**Q: 如何在多个工具间共享代码？**

A: 使用继承或工具函数：

```python
# utils.py
def format_retrieval_results(docs: list, style: str) -> str:
    """共享的格式化函数"""
    pass

# agent_tool.py
from utils import format_retrieval_results

class LargeRAGTool:
    def _format_results(self, docs):
        return format_retrieval_results(docs, self.format_style)
```

**Q: 扩展会影响性能吗？**

A: 只在需要时启用扩展功能：

```python
class LargeRAGTool:
    def __init__(self, enable_stats: bool = False):
        self.enable_stats = enable_stats

    def retrieve(self, query: str, **kwargs) -> str:
        if self.enable_stats:
            self._update_stats()  # 只在启用时执行
```

---

## 总结

本扩展指南涵盖了 7 个常见扩展场景，从简单的统计追踪到复杂的多工具统一接口。建议：

1. **按需扩展**：只实现当前需要的功能
2. **保持简洁**：优先考虑子类或工具函数
3. **向后兼容**：确保扩展不破坏现有代码
4. **充分测试**：每次扩展后验证功能

记住：**精简版的价值在于简单直接，扩展时保持这一特性至关重要**。
