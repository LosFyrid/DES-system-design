"""
增量构建索引脚本 V2 - 使用文档级缓存和批量写入
支持真正的断点续传

运行方式：
    python scripts/build_index_v2.py --literature-dir data/DES_v1_7445 --collection-name des_prod_v1 --batch-size 500
"""

import sys
import argparse
from pathlib import Path
import logging

# 添加项目路径
project_root = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(project_root))

from src.tools.largerag.core.document_processor import DocumentProcessor
from src.tools.largerag.core.indexer_v2 import LargeRAGIndexerV2

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description='增量构建向量索引 (V2 - 文档级缓存)')
    parser.add_argument('--literature-dir', required=True, help='文献目录')
    parser.add_argument('--collection-name', default='des_prod_v1', help='Collection名称')
    parser.add_argument('--batch-size', type=int, default=500, help='每批写入的nodes数量（非文献数）')
    parser.add_argument('--aggregate-small-chunks', action='store_true', help='聚合JSON chunks')

    args = parser.parse_args()

    logger.info("="*80)
    logger.info("  增量构建向量索引 V2")
    logger.info("="*80)
    logger.info(f"\n配置:")
    logger.info(f"  文献目录: {args.literature_dir}")
    logger.info(f"  Collection: {args.collection_name}")
    logger.info(f"  批量写入: 每{args.batch_size}个nodes写一次")
    logger.info(f"  聚合chunks: {args.aggregate_small_chunks}")

    # 验证文献目录
    lit_path = Path(args.literature_dir)
    if not lit_path.exists():
        logger.error(f"文献目录不存在: {args.literature_dir}")
        return False

    # 初始化组件
    logger.info("\n初始化组件...")
    doc_processor = DocumentProcessor(aggregate_small_chunks=args.aggregate_small_chunks)
    indexer = LargeRAGIndexerV2(collection_name=args.collection_name)

    # 加载所有文档
    logger.info("\n加载文献文档...")
    documents = doc_processor.process_from_folders(str(lit_path))
    logger.info(f"加载完成: {len(documents)} 个文档")

    # 增量构建索引
    index = indexer.build_index_incremental(
        documents=documents,
        batch_write_size=args.batch_size,
        show_progress=True
    )

    # 最终统计
    stats = indexer.get_index_stats()
    logger.info(f"\n{'='*80}")
    logger.info(f"📊 最终索引统计:")
    logger.info(f"  Collection: {stats['collection_name']}")
    logger.info(f"  总向量数: {stats['document_count']:,}")
    logger.info(f"  数据库位置: {stats['persist_directory']}")

    if 'cache_stats' in stats:
        cache_stats = stats['cache_stats']
        logger.info(f"\n📦 缓存统计:")
        logger.info(f"  缓存目录: {cache_stats['cache_dir']}")
        logger.info(f"  已缓存文档: {cache_stats['cached_documents']}")
        logger.info(f"  缓存大小: {cache_stats['total_size_mb']} MB")

    logger.info(f"{'='*80}\n")

    return True


if __name__ == "__main__":
    try:
        success = main()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        logger.warning("\n\n⚠️  用户中断")
        logger.info("已处理的文档已保存到Chroma和缓存，可以重新运行继续")
        sys.exit(1)
    except Exception as e:
        logger.error(f"\n❌ 错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
