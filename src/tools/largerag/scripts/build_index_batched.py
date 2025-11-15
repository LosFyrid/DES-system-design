"""
分批构建索引脚本
每500篇文献立即写入数据库，降低中断风险

运行方式：
    python scripts/build_index_batched.py --literature-dir data/DES_v1_7445 --collection-name des_prod_v1 --batch-size 500
"""

import sys
import time
import argparse
from pathlib import Path
from datetime import datetime
import logging

# 添加项目路径
project_root = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(project_root))

from src.tools.largerag.core.document_processor import DocumentProcessor
from src.tools.largerag.core.indexer import LargeRAGIndexer
from src.tools.largerag.config.settings import SETTINGS

import chromadb
from llama_index.core import StorageContext
from llama_index.vector_stores.chroma import ChromaVectorStore

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def get_processed_doc_hashes(collection) -> set:
    """从现有collection中提取已处理的文献哈希"""
    try:
        # 获取所有documents的metadata
        results = collection.get(include=['metadatas'])
        metadatas = results.get('metadatas', [])

        doc_hashes = set()
        for meta in metadatas:
            if meta and 'doc_hash' in meta:
                doc_hashes.add(meta['doc_hash'])

        return doc_hashes
    except:
        return set()


def main():
    parser = argparse.ArgumentParser(description='分批构建向量索引')
    parser.add_argument('--literature-dir', required=True, help='文献目录')
    parser.add_argument('--collection-name', default='des_prod_v1', help='Collection名称')
    parser.add_argument('--batch-size', type=int, default=500, help='每批处理的文献数量')
    parser.add_argument('--aggregate-small-chunks', action='store_true', help='聚合JSON chunks')

    args = parser.parse_args()

    logger.info("="*80)
    logger.info("  分批构建向量索引")
    logger.info("="*80)
    logger.info(f"\n配置:")
    logger.info(f"  文献目录: {args.literature_dir}")
    logger.info(f"  Collection: {args.collection_name}")
    logger.info(f"  批次大小: {args.batch_size} 篇/批")
    logger.info(f"  聚合chunks: {args.aggregate_small_chunks}")

    # 验证文献目录
    lit_path = Path(args.literature_dir)
    if not lit_path.exists():
        logger.error(f"文献目录不存在: {args.literature_dir}")
        return False

    all_folders = sorted([f for f in lit_path.iterdir() if f.is_dir()])
    total_papers = len(all_folders)
    logger.info(f"  总文献数: {total_papers}")

    # 初始化组件
    logger.info("\n初始化组件...")
    doc_processor = DocumentProcessor(aggregate_small_chunks=args.aggregate_small_chunks)
    indexer = LargeRAGIndexer(collection_name=args.collection_name)

    # 检查已处理的文献
    chroma_client = chromadb.PersistentClient(path=SETTINGS.vector_store.persist_directory)

    try:
        collection = chroma_client.get_collection(name=args.collection_name)
        existing_count = collection.count()
        processed_hashes = get_processed_doc_hashes(collection)
        logger.info(f"\n检测到已有索引:")
        logger.info(f"  现有向量数: {existing_count:,}")
        logger.info(f"  已处理文献: {len(processed_hashes)} 篇")
    except:
        processed_hashes = set()
        logger.info(f"\n未检测到已有索引，将从头构建")

    # 筛选未处理的文献
    remaining_folders = [f for f in all_folders if f.name not in processed_hashes]
    logger.info(f"\n待处理文献: {len(remaining_folders)} 篇")

    if not remaining_folders:
        logger.info("✓ 所有文献已处理完成！")
        return True

    # 分批处理
    total_batches = (len(remaining_folders) + args.batch_size - 1) // args.batch_size
    logger.info(f"将分为 {total_batches} 个批次处理\n")

    start_time = time.time()
    total_new_nodes = 0

    for batch_idx in range(total_batches):
        batch_start = batch_idx * args.batch_size
        batch_end = min((batch_idx + 1) * args.batch_size, len(remaining_folders))
        batch_folders = remaining_folders[batch_start:batch_end]

        logger.info("="*80)
        logger.info(f"  批次 {batch_idx + 1}/{total_batches}")
        logger.info(f"  处理文献 {batch_start + 1}-{batch_end} / {len(remaining_folders)}")
        logger.info("="*80)

        batch_start_time = time.time()

        # 处理本批文献
        batch_documents = []
        for folder in batch_folders:
            content_file = folder / "content_list_process.json"
            article_file = folder / "article.json"

            try:
                if content_file.exists():
                    docs = doc_processor._load_from_content_list(content_file, folder.name)
                    batch_documents.extend(docs)
                elif article_file.exists():
                    docs = doc_processor._load_from_article(article_file, folder.name)
                    batch_documents.extend(docs)
            except Exception as e:
                logger.error(f"处理文献 {folder.name} 失败: {e}")
                continue

        if not batch_documents:
            logger.warning(f"批次 {batch_idx + 1} 无有效文档，跳过")
            continue

        logger.info(f"\n处理 {len(batch_documents)} 个文档...")

        # 运行pipeline（parsing + embedding）
        try:
            nodes = indexer.pipeline.run(documents=batch_documents, show_progress=True)
            logger.info(f"生成 {len(nodes)} 个nodes")
        except Exception as e:
            logger.error(f"Pipeline处理失败: {e}")
            logger.info("已处理的批次已保存，可以重新运行继续")
            return False

        # 写入Chroma
        logger.info(f"写入Chroma数据库...")
        try:
            # 获取或创建collection
            collection = chroma_client.get_or_create_collection(
                name=args.collection_name,
                metadata={"hnsw:space": SETTINGS.vector_store.distance_metric}
            )
            vector_store = ChromaVectorStore(chroma_collection=collection)
            storage_context = StorageContext.from_defaults(vector_store=vector_store)

            # 批量添加nodes
            from llama_index.core import VectorStoreIndex
            index = VectorStoreIndex(
                nodes=nodes,
                storage_context=storage_context,
                embed_model=indexer.embed_model,
                show_progress=False,
            )

            total_new_nodes += len(nodes)

        except Exception as e:
            logger.error(f"写入Chroma失败: {e}")
            logger.info("已处理的批次已保存，可以重新运行继续")
            return False

        # 批次完成统计
        batch_time = time.time() - batch_start_time
        elapsed = time.time() - start_time
        avg_time_per_batch = elapsed / (batch_idx + 1)
        remaining_batches = total_batches - (batch_idx + 1)
        eta = avg_time_per_batch * remaining_batches

        logger.info(f"\n✓ 批次 {batch_idx + 1} 完成")
        logger.info(f"  批次耗时: {batch_time/60:.1f} 分钟")
        logger.info(f"  已用时间: {elapsed/60:.1f} 分钟")
        logger.info(f"  预计剩余: {eta/60:.1f} 分钟")
        logger.info(f"  累计新增: {total_new_nodes:,} nodes")

        # 获取当前总数
        current_total = collection.count()
        logger.info(f"  数据库总计: {current_total:,} vectors\n")

    # 完成统计
    total_time = time.time() - start_time
    logger.info("="*80)
    logger.info("  ✅ 全部完成！")
    logger.info("="*80)
    logger.info(f"\n📊 最终统计:")
    logger.info(f"  Collection: {args.collection_name}")
    logger.info(f"  新处理文献: {len(remaining_folders)} 篇")
    logger.info(f"  新增nodes: {total_new_nodes:,}")
    logger.info(f"  总耗时: {total_time/60:.1f} 分钟 ({total_time/3600:.2f} 小时)")

    # 最终验证
    collection = chroma_client.get_collection(name=args.collection_name)
    final_count = collection.count()
    logger.info(f"  数据库总向量: {final_count:,}")
    logger.info(f"\n数据库位置: {SETTINGS.vector_store.persist_directory}")
    logger.info("="*80 + "\n")

    return True


if __name__ == "__main__":
    try:
        success = main()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        logger.warning("\n\n⚠️  用户中断")
        logger.info("已处理的批次已保存到Chroma，可以重新运行继续")
        sys.exit(1)
    except Exception as e:
        logger.error(f"\n❌ 错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
