# LargeRAG 缓存机制说明

## 概述

LargeRAG 提供 **本地文件缓存** 和 **Redis 缓存** 两种方式，用于缓存文档的 embedding 向量，避免重复调用 API。

## 为什么需要缓存？

### 使用场景

1. **调试/测试**：开发时多次运行索引，避免重复计算
2. **索引失败重试**：网络中断后重新索引，已完成的部分直接读缓存
3. **增量索引**：添加新文献时，老文献的 embedding 直接使用缓存
4. **节省成本**：避免重复调用 DashScope API（���调用量计费）

### 性能提升

- **API调用**: ~100ms/batch
- **缓存读取**: <1ms
- **重复索引加速**: 100倍+

---

## 缓存方案对比

| 特性 | 本地文件缓存（推荐） | Redis 缓存 |
|------|---------------------|-----------|
| **部署难度** | ⭐ 无需额外服务 | ⭐⭐⭐ 需要 Redis 服务 |
| **速度** | ⭐⭐⭐ 快 | ⭐⭐⭐⭐ 更快（内存） |
| **持久化** | ⭐⭐⭐⭐ 自动持久化 | ⭐⭐ 需要配置 RDB/AOF |
| **分布式** | ❌ 仅单机 | ✅ 支持多机共享 |
| **适用场景** | 单机部署、简化架构 | 多机部署、高并发 |

---

## 本地文件缓存（默认）

### 配置方式

`config/settings.yaml`:
```yaml
cache:
  enabled: true
  type: "local"
  local_cache_dir: "${PROJECT_ROOT}src/tools/largerag/data/cache"
  collection_name: "largerag_embedding_cache"
```

### 工作原理

1. 首次索引：计算 embedding 并保存���本地文件（pickle 格式）
2. 重复索引：检查缓存，如果存在直接读取，否则调用 API
3. 缓存键：基于文档内容的 MD5 哈希，确保唯一性

### 文件结构

```
data/cache/
└── largerag_embedding_cache/
    ├── a1b2c3d4e5f6...pkl  # 文档1的embedding
    ├── f6e5d4c3b2a1...pkl  # 文档2的embedding
    └── ...
```

### 缓存管理

```python
from core.cache import LocalFileCache

cache = LocalFileCache(
    cache_dir="data/cache",
    collection_name="largerag_embedding_cache"
)

# 查看缓存统计
stats = cache.get_stats()
print(f"缓存文件数: {stats['file_count']}")
print(f"总大小: {stats['total_size_mb']} MB")

# 清空缓存
cache.clear()
```

### 优点

- ✅ **零依赖**：无需安装 Redis
- ✅ **简单可靠**：文件系统天然持久化
- ✅ **易于备份**：直接复制目录即可
- ✅ **可视化**：可以直接查看缓存文件

### 注意事项

- 缓存文件会��用磁盘空间（35篇文献约 5-10MB）
- 首次索引仍需完整计算 embedding
- 文档内容变化后，缓存会自动失效（基于内容哈希）

---

## Redis 缓存（可选）

### 适用场景

- 多机分布式部署
- 需要跨进程共享缓存
- 对读写速度要求极高

### 配置方式

**1. 安装 Redis 依赖**

取消 `requirements.txt` 中的注释：
```txt
llama-index-storage-kvstore-redis>=0.2.0
redis>=5.0.0
```

运行：
```bash
pip install llama-index-storage-kvstore-redis redis
```

**2. 启动 Redis 服务**

```bash
# macOS/Linux
redis-server

# Windows (需先安装 Redis)
redis-server.exe
```

**3. 修改配置**

`config/settings.yaml`:
```yaml
cache:
  enabled: true
  type: "redis"  # 改为 redis
  redis_host: "localhost"
  redis_port: 6379
  collection_name: "largerag_embedding_cache"
```

### 验证 Redis 连接

```bash
redis-cli ping
# 输出: PONG（表示连接成功）
```

### 优点

- ✅ **高速**：内存存储，读写极快
- ✅ **分布式**：多机共享缓存
- ✅ **TTL支持**：自动过期清理

### 注意事项

- ⚠️ 需要维护额外服务（Redis）
- ⚠️ 需要配置持久化（否则重启丢失）
- ⚠️ 内存占用较大

---

## 禁用缓存

如果不需要缓存（例如：只索引一次，永不重复），可以禁用：

`config/settings.yaml`:
```yaml
cache:
  enabled: false  # 禁用缓存
```

---

## 常见问题

### Q1: 缓存会过期吗？

- **本地文件缓存**：不会自动过期，手动删除文件即可清理
- **Redis 缓存**：可以配置 `ttl` 参数（秒），超时自动删除

### Q2: 缓存占用多大空间？

- 每个文档节点约 4KB（1024维向量 × 4字节）
- 2831个节点（35篇文献）≈ 11MB

### Q3: 如何清空缓存？

**本地文件缓存**：
```bash
rm -rf src/tools/largerag/data/cache
```

**Redis 缓存**：
```bash
redis-cli FLUSHDB
```

### Q4: 缓存会影响检索结果吗？

不会。缓存只存储 embedding 向量，不影响检索逻辑。

### Q5: 多机部署如何共享缓存？

使用 Redis 缓存，所有机器连接同一个 Redis 服务器即可。

---

## 最佳实践

1. **开发/测试阶段**：启用本地文件缓存，加速迭代
2. **生产环境**：根据部署方式选择：
   - 单机：本地文件缓存
   - 多机：Redis 缓存
3. **定期清理**：旧文献更新后，清空对应缓存
4. **监控缓存大小**：避免占用过多磁盘/内存

---

## 缓存统计信息

通过 API 查看缓存使用情况：

```python
from largerag import LargeRAG

rag = LargeRAG()
stats = rag.get_stats()

print(stats)
# 输出包含缓存命中率、文件数量等信息
```

---

## 总结

- **推荐配置**：本地文件缓存（`type: local`）
- **优势**：零依赖、简单可靠、适合大部分场景
- **升级路径**：需要分布式时再切换到 Redis
