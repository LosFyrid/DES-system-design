"""
LargeRAG 示例 1: 构建索引
====================================

功能展示：
1. 初始化 LargeRAG
2. 从文件夹结构加载文献数据
3. 构建向量索引（含缓存、批处理）
4. 查看索引统计信息
5. 展示文档处理细节（元数据、分块）

运行方式：
    python examples/1_build_index.py
"""

import sys
import time
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from largerag import LargeRAG


def print_section(title: str):
    """打印分隔线"""
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


def main():
    print_section("LargeRAG 索引构建示例")

    # ============================================================
    # 1. 初始化 LargeRAG
    # ============================================================
    print_section("步骤 1: 初始化 LargeRAG")

    print("\n初始化配置来源:")
    print("  - 配置文件: config/settings.yaml")
    print("  - API Key: .env 文件中的 DASHSCOPE_API_KEY")
    print("  - 向量数据库: Chroma (持久化存储)")
    print("  - 缓存系统: 本地文件缓存 (可选 Redis)")

    start_time = time.time()
    rag = LargeRAG()
    init_time = time.time() - start_time

    print(f"\n✓ 初始化完成 (耗时: {init_time:.2f}秒)")

    # 检查是否已有索引
    if rag.query_engine is not None:
        print("  ⚠️  检测到已有索引，本次运行将覆盖旧索引")
        existing_stats = rag.get_stats()
        print(f"  现有索引节点数: {existing_stats['index_stats'].get('document_count', 0)}")
    else:
        print("  ℹ️  未检测到已有索引，将从头构建")

    # ============================================================
    # 2. 指定文献目录
    # ============================================================
    print_section("步骤 2: 准备文献数据")

    literature_dir = str(Path(__file__).parent.parent / "data" / "test_5papers")

    print(f"\n文献目录: {literature_dir}")
    print("\n文件夹结构说明:")
    print("  data/literature/")
    print("    ├── {hash1}/")
    print("    │   ├── content_list_process.json  ← 优先使用")
    print("    │   ├── article.json               ← 备选")
    print("    │   ├── {hash1}.md                 (不使用)")
    print("    │   └── images/                    (不处理)")
    print("    └── {hash2}/")
    print("        └── ...")

    # 统计文献数量
    lit_path = Path(literature_dir)
    if lit_path.exists():
        folder_count = len([d for d in lit_path.iterdir() if d.is_dir()])
        print(f"\n✓ 检测到 {folder_count} 个文献文件夹")
    else:
        print(f"\n✗ 错误: 文献目录不存在: {literature_dir}")
        return False

    # ============================================================
    # 3. 构建索引（关键步骤）
    # ============================================================
    print_section("步骤 3: 构建向量索引")

    print("\n索引构建流程:")
    print("  [1] 文档加载      - 从 JSON 提取文本段落")
    print("  [2] 文档分块      - SentenceSplitter (chunk_size=512, overlap=50)")
    print("  [3] Embedding     - DashScope text-embedding-v3 (1024维)")
    print("  [4] 缓存检查      - 跳过已计算的 embedding (节省API调用)")
    print("  [5] 向量存储      - 持久化到 Chroma 数据库")

    print("\n开始构建索引...\n")

    start_time = time.time()
    success = rag.index_from_folders(literature_dir)
    index_time = time.time() - start_time

    if not success:
        print("\n✗ 索引构建失败，请检查日志")
        return False

    print(f"\n✓ 索引构建成功 (总耗时: {index_time:.2f}秒 / {index_time/60:.2f}分钟)")

    # 性能参考
    print("\n性能参考:")
    print(f"  - 实际耗时: {index_time:.2f}秒")
    print(f"  - 性能目标: <180秒 (3分钟) for 35篇文献")
    if index_time < 180:
        print(f"  ✅ 性能达标！")
    else:
        print(f"  ⚠️  超出目标 {index_time-180:.1f}秒")

    # ============================================================
    # 4. 查看索引统计信息
    # ============================================================
    print_section("步骤 4: 索引统计信息")

    stats = rag.get_stats()

    # 4.1 索引统计
    print("\n📊 向量索引统计:")
    index_stats = stats['index_stats']
    print(f"  Collection 名称: {index_stats.get('collection_name', 'N/A')}")
    print(f"  索引节点数:      {index_stats.get('document_count', 0)}")
    print(f"  存储位置:        {index_stats.get('persist_directory', 'N/A')}")

    print("\n  说明:")
    print("  - 节点数 = 文档分块后的片段数量")
    print("  - 每个节点包含 ~512 tokens 的文本 + 1024维向量")

    # 4.2 文档处理统计
    print("\n📊 文档处理统计:")
    doc_stats = stats['doc_processing_stats']
    processed = doc_stats.get('processed', 0)
    skipped = doc_stats.get('skipped', 0)
    total = doc_stats.get('total', 0)

    print(f"  已处理文档段落: {processed}")
    print(f"  跳过文档:        {skipped}")
    print(f"  总计:            {total}")

    if total > 0:
        success_rate = (processed / total) * 100
        print(f"  成功率:          {success_rate:.2f}%")

        if success_rate >= 95:
            print(f"  ✅ 成功率达标 (目标: >95%)")
        else:
            print(f"  ⚠️  成功率不足 {95-success_rate:.1f}%")

    print("\n  说明:")
    print("  - 段落数 ≠ 节点数（因为会进一步分块）")
    print("  - 跳过的文档可能是空文本或格式错误")

    # ============================================================
    # 5. 展示文档处理细节
    # ============================================================
    print_section("步骤 5: 文档处理细节展示")

    print("\n从索引中采样 3 个节点，展示元数据和内容:")

    # 使用一个简单查询来获取一些节点
    sample_docs = rag.get_similar_docs("deep eutectic solvents", top_k=3)

    for i, doc in enumerate(sample_docs, 1):
        print(f"\n--- 节点 {i} ---")
        print(f"相似度分数: {doc['score']:.4f}")

        metadata = doc['metadata']
        print(f"\n元数据:")
        print(f"  文档哈希:   {metadata.get('doc_hash', 'N/A')[:16]}...")
        print(f"  来源文件:   {metadata.get('source_file', 'N/A')}")
        print(f"  页码:       {metadata.get('page_idx', 'N/A')}")
        print(f"  文本层级:   {metadata.get('text_level', 'N/A')}")
        print(f"  含引用:     {metadata.get('has_citations', 'N/A')}")

        text = doc['text']
        print(f"\n文本内容 (前200字符):")
        print(f"  {text[:200]}...")
        print(f"  [总长度: {len(text)} 字符]")

    # ============================================================
    # 6. 缓存系统说明
    # ============================================================
    print_section("步骤 6: 缓存系统说明")

    print("\n缓存机制:")
    print("  ✓ 本地文件缓存已启用 (config/settings.yaml: cache.enabled=true)")
    print("  ✓ 缓存类型: 本地文件 (type=local)")
    print("  ✓ 缓存位置: src/tools/largerag/data/cache/")

    print("\n缓存工作原理:")
    print("  1. 首次索引: 计算 embedding 并保存到本地文件 (pickle 格式)")
    print("  2. 重复索引: 检查缓存，如果存在直接读取，否则调用 API")
    print("  3. 缓存键:   基于文档内容的哈希，确保唯一性")

    print("\n缓存优势:")
    print("  ✓ 避免重复调用 DashScope API (节省成本)")
    print("  ✓ 加速重复索引 (100倍+ 速度提升)")
    print("  ✓ 支持增量索引 (新增文献时老文献用缓存)")

    print("\n提示:")
    print("  - 再次运行本脚本将使用缓存，速度会大幅提升")
    print("  - 如需清空缓存: rm -rf src/tools/largerag/data/cache")

    # ============================================================
    # 7. 下一步操作
    # ============================================================
    print_section("完成！")

    print("\n✅ 索引构建完成，现在可以:")
    print("  1. 运行查询示例: python examples/2_query_and_retrieve.py")
    print("  2. 在代码中使用:")
    print("      from largerag import LargeRAG")
    print("      rag = LargeRAG()  # 自动加载已有索引")
    print("      answer = rag.query('你的问题')")

    print("\n索引文件位置:")
    print(f"  {index_stats.get('persist_directory', 'N/A')}")
    print("  (Chroma 数据库会自动持久化，重启后自动加载)")

    print("\n" + "=" * 70 + "\n")

    return True


if __name__ == "__main__":
    try:
        success = main()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n⚠️  用户中断")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
