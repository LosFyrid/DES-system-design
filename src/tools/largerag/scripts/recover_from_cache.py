"""
从昨晚的缓存恢复索引并增量处理剩余文献

功能：
1. 加载缓存文件中的29.3万个nodes（已有embeddings）
2. 反序列化并写入Chroma数据库
3. 识别已处理的文献
4. 增量处理剩余4510篇文献
5. 全部写入同一个collection

运行方式：
    python scripts/recover_from_cache.py
"""

import sys
import pickle
import time
from pathlib import Path
from typing import List, Set
import logging

# 添加项目路径
project_root = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(project_root))

from llama_index.core.schema import BaseNode
from llama_index.core import VectorStoreIndex, Document, StorageContext
from llama_index.vector_stores.chroma import ChromaVectorStore
import chromadb

from src.tools.largerag.config.settings import SETTINGS
from src.tools.largerag.core.document_processor import DocumentProcessor
from src.tools.largerag.core.indexer import LargeRAGIndexer

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def load_cached_nodes(cache_file: Path) -> List[BaseNode]:
    """
    从缓存文件加载nodes并反序列化

    Args:
        cache_file: 缓存文件路径

    Returns:
        反序列化后的BaseNode列表
    """
    logger.info(f"加载缓存文件: {cache_file}")

    with open(cache_file, 'rb') as f:
        cache_data = pickle.load(f)

    # 缓存格式: {'nodes': [serialized_node_dict, ...]}
    nodes_data = cache_data.get('nodes', [])
    logger.info(f"缓存中包含 {len(nodes_data)} 个序列化的nodes")

    # 反序列化nodes
    nodes = []
    for i, node_dict in enumerate(nodes_data):
        try:
            # LlamaIndex使用 __type__ 和 __data__ 进行序列化
            node = BaseNode.from_dict(node_dict)
            nodes.append(node)

            if (i + 1) % 10000 == 0:
                logger.info(f"  已反序列化 {i + 1}/{len(nodes_data)} 个nodes...")
        except Exception as e:
            logger.error(f"反序列化node {i} 失败: {e}")
            continue

    logger.info(f"✓ 成功反序列化 {len(nodes)} 个nodes")
    return nodes


def extract_processed_doc_hashes(nodes: List[BaseNode]) -> Set[str]:
    """
    从nodes的metadata中提取已处理的文献哈希

    Args:
        nodes: BaseNode列表

    Returns:
        已处理的文献哈希集合
    """
    doc_hashes = set()
    for node in nodes:
        metadata = node.metadata
        if 'doc_hash' in metadata:
            doc_hashes.add(metadata['doc_hash'])

    logger.info(f"从缓存中识别出 {len(doc_hashes)} 篇已处理的文献")
    return doc_hashes


def write_nodes_to_chroma(
    nodes: List[BaseNode],
    collection_name: str,
    chroma_client: chromadb.PersistentClient,
    indexer: LargeRAGIndexer
) -> VectorStoreIndex:
    """
    将nodes写入Chroma数据库

    Args:
        nodes: 要写入的nodes
        collection_name: collection名称
        chroma_client: Chroma客户端
        indexer: LargeRAGIndexer实例（用于获取embed_model）

    Returns:
        VectorStoreIndex对象
    """
    logger.info(f"创建Chroma collection: {collection_name}")

    # 创建或获取collection
    collection = chroma_client.get_or_create_collection(
        name=collection_name,
        metadata={"hnsw:space": SETTINGS.vector_store.distance_metric}
    )

    vector_store = ChromaVectorStore(chroma_collection=collection)
    storage_context = StorageContext.from_defaults(vector_store=vector_store)

    logger.info(f"写入 {len(nodes)} 个nodes到Chroma...")

    # 创建索引（nodes已包含embeddings）
    index = VectorStoreIndex(
        nodes=nodes,
        storage_context=storage_context,
        embed_model=indexer.embed_model,
        show_progress=True,
    )

    logger.info("✓ Nodes成功写入Chroma")
    return index


def process_remaining_literature(
    literature_dir: str,
    processed_doc_hashes: Set[str],
    indexer: LargeRAGIndexer,
    collection_name: str,
    chroma_client: chromadb.PersistentClient
) -> int:
    """
    增量处理剩余的文献

    Args:
        literature_dir: 文献目录
        processed_doc_hashes: 已处理的文献哈希集合
        indexer: LargeRAGIndexer实例
        collection_name: collection名称
        chroma_client: Chroma客户端

    Returns:
        新处理的文献数量
    """
    logger.info("="*80)
    logger.info("开始增量处理剩余文献")
    logger.info("="*80)

    lit_path = Path(literature_dir)
    all_folders = sorted([f for f in lit_path.iterdir() if f.is_dir()])

    # 筛选出未处理的文献
    remaining_folders = [f for f in all_folders if f.name not in processed_doc_hashes]

    logger.info(f"总文献数: {len(all_folders)}")
    logger.info(f"已处理: {len(processed_doc_hashes)}")
    logger.info(f"待处理: {len(remaining_folders)}")

    if not remaining_folders:
        logger.info("✓ 所有文献已处理完成！")
        return 0

    # 处理剩余文献
    doc_processor = DocumentProcessor(aggregate_small_chunks=True)

    logger.info("\n开始处理剩余文献...")
    logger.info(f"预估时间: 根据API限额，可能需要数小时\n")

    start_time = time.time()

    # 逐个处理文献并追加到Chroma
    collection = chroma_client.get_collection(name=collection_name)
    vector_store = ChromaVectorStore(chroma_collection=collection)
    storage_context = StorageContext.from_defaults(vector_store=vector_store)

    # 分批处理（避免内存占用过大）
    batch_size = 100
    total_new_nodes = 0

    for i in range(0, len(remaining_folders), batch_size):
        batch_folders = remaining_folders[i:i+batch_size]
        batch_num = i // batch_size + 1
        total_batches = (len(remaining_folders) + batch_size - 1) // batch_size

        logger.info(f"\n{'='*60}")
        logger.info(f"批次 {batch_num}/{total_batches}")
        logger.info(f"处理文献 {i+1}-{min(i+batch_size, len(remaining_folders))}/{len(remaining_folders)}")
        logger.info(f"{'='*60}")

        # 处理本批文献
        batch_documents = []
        for folder in batch_folders:
            content_file = folder / "content_list_process.json"
            article_file = folder / "article.json"

            if content_file.exists():
                docs = doc_processor._load_from_content_list(content_file, folder.name)
                batch_documents.extend(docs)
            elif article_file.exists():
                docs = doc_processor._load_from_article(article_file, folder.name)
                batch_documents.extend(docs)

        if not batch_documents:
            logger.warning(f"批次 {batch_num} 无有效文档，跳过")
            continue

        # 构建索引（会自动计算embedding并追加到Chroma）
        logger.info(f"处理 {len(batch_documents)} 个文档...")
        batch_nodes = indexer.pipeline.run(documents=batch_documents, show_progress=True)

        # 追加到索引
        logger.info(f"追加 {len(batch_nodes)} 个nodes到Chroma...")
        for node in batch_nodes:
            vector_store.add([node])

        total_new_nodes += len(batch_nodes)

        elapsed = time.time() - start_time
        avg_time_per_batch = elapsed / batch_num
        remaining_batches = total_batches - batch_num
        eta = avg_time_per_batch * remaining_batches

        logger.info(f"✓ 批次 {batch_num} 完成")
        logger.info(f"  已用时间: {elapsed/60:.1f} 分钟")
        logger.info(f"  预计剩余: {eta/60:.1f} 分钟")
        logger.info(f"  累计新增: {total_new_nodes} nodes")

    total_time = time.time() - start_time
    logger.info(f"\n{'='*80}")
    logger.info(f"✓ 增量处理完成！")
    logger.info(f"  新处理文献: {len(remaining_folders)} 篇")
    logger.info(f"  新增nodes: {total_new_nodes} 个")
    logger.info(f"  总耗时: {total_time/60:.1f} 分钟 ({total_time/3600:.2f} 小时)")
    logger.info(f"{'='*80}")

    return len(remaining_folders)


def main():
    """主函数"""
    logger.info("="*80)
    logger.info("  从缓存恢复并增量构建索引")
    logger.info("="*80)

    # 配置参数
    CACHE_FILE = Path("src/tools/largerag/data/prod_cache/largerag_embedding_cache/2726c8573978c6cf17f8d7b71bae8a66.pkl")
    LITERATURE_DIR = "src/tools/largerag/data/DES_v1_7445"
    COLLECTION_NAME = "des_prod_v1"

    logger.info(f"\n配置:")
    logger.info(f"  缓存文件: {CACHE_FILE}")
    logger.info(f"  文献目录: {LITERATURE_DIR}")
    logger.info(f"  Collection: {COLLECTION_NAME}")

    # 步骤1: 加载缓存的nodes
    logger.info(f"\n{'='*80}")
    logger.info("步骤 1/4: 加载缓存nodes")
    logger.info(f"{'='*80}")

    if not CACHE_FILE.exists():
        logger.error(f"缓存文件不存在: {CACHE_FILE}")
        return False

    cached_nodes = load_cached_nodes(CACHE_FILE)

    if not cached_nodes:
        logger.error("缓存为空，无法继续")
        return False

    # 步骤2: 提取已处理的文献
    logger.info(f"\n{'='*80}")
    logger.info("步骤 2/4: 识别已处理的文献")
    logger.info(f"{'='*80}")

    processed_doc_hashes = extract_processed_doc_hashes(cached_nodes)

    # 步骤3: 写入Chroma
    logger.info(f"\n{'='*80}")
    logger.info("步骤 3/4: 写入缓存nodes到Chroma")
    logger.info(f"{'='*80}")

    # 初始化indexer（需要embed_model）
    indexer = LargeRAGIndexer(collection_name=COLLECTION_NAME)
    chroma_client = chromadb.PersistentClient(
        path=SETTINGS.vector_store.persist_directory
    )

    index = write_nodes_to_chroma(
        nodes=cached_nodes,
        collection_name=COLLECTION_NAME,
        chroma_client=chroma_client,
        indexer=indexer
    )

    logger.info(f"✓ 已写入 {len(cached_nodes)} 个nodes")

    # 步骤4: 增量处理剩余文献
    logger.info(f"\n{'='*80}")
    logger.info("步骤 4/4: 增量处理剩余文献")
    logger.info(f"{'='*80}")

    new_count = process_remaining_literature(
        literature_dir=LITERATURE_DIR,
        processed_doc_hashes=processed_doc_hashes,
        indexer=indexer,
        collection_name=COLLECTION_NAME,
        chroma_client=chroma_client
    )

    # 完成统计
    logger.info(f"\n{'='*80}")
    logger.info("  ✅ 全部完成！")
    logger.info(f"{'='*80}")

    # 获取最终统计
    collection = chroma_client.get_collection(name=COLLECTION_NAME)
    final_count = collection.count()

    logger.info(f"\n📊 最终统计:")
    logger.info(f"  Collection: {COLLECTION_NAME}")
    logger.info(f"  总向量数: {final_count:,}")
    logger.info(f"  缓存恢复: {len(cached_nodes):,} nodes")
    logger.info(f"  新增处理: {new_count} 篇文献")
    logger.info(f"\n数据库位置:")
    logger.info(f"  {SETTINGS.vector_store.persist_directory}")
    logger.info(f"\n{'='*80}\n")

    return True


if __name__ == "__main__":
    try:
        success = main()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        logger.warning("\n\n⚠️  用户中断")
        logger.info("进度已保存到Chroma，可以使用LargeRAG正常加载")
        sys.exit(1)
    except Exception as e:
        logger.error(f"\n❌ 错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
