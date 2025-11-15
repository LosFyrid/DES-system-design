"""
LargeRAG 向量索引构建工具
====================================

功能：
1. 从指定文献目录构建向量索引
2. 支持命令行参数覆盖配置
3. 支持断点续传（通过缓存）
4. 输出详细日志到文件

运行方式：
    # 基本运行（必须指定文献目录）
    python scripts/build_index.py --literature-dir data/literature_production

    # 指定 collection 名称
    python scripts/build_index.py --literature-dir data/literature_production --collection-name des_production_v1

    # 强制重建索引
    python scripts/build_index.py --literature-dir data/literature_production --rebuild

    # 禁用缓存（确保使用最新配置）
    python scripts/build_index.py --literature-dir data/literature_production --rebuild --no-cache

    # 覆盖文档处理配置
    python scripts/build_index.py --literature-dir data/literature --chunk-size 1024 --chunk-overlap 100

    # 查看帮助
    python scripts/build_index.py --help

可覆盖的配置参数：
    文档处理配置：
      --splitter-type TYPE           分块策略 (token/semantic/sentence)
      --chunk-size N                 文档分块大小
      --chunk-overlap N              文档分块重叠大小
      --separator STR                分块分隔符
      --aggregate-small-chunks       聚合JSON文件内的所有片段
      --semantic-breakpoint-threshold F  语义断点阈值 (0-1)
      --semantic-buffer-size N       语义缓冲区大小

    向量存储配置：
      --collection-name NAME         集合名称
      --distance-metric METRIC       距离度量 (cosine/l2/ip)

    其他：
      --rebuild                      强制重建索引
      --no-cache                     禁用缓存
"""

import sys
import time
import json
import argparse
import logging
from pathlib import Path
from datetime import datetime
from dataclasses import asdict

# 添加项目根目录到sys.path
# build_index.py → scripts → largerag → tools → src → PROJECT_ROOT
project_root = Path(__file__).resolve().parents[4]  # 往上4级
sys.path.insert(0, str(project_root))

from src.tools.largerag import LargeRAG
from src.tools.largerag.config.settings import SETTINGS


def setup_logging(log_dir: Path) -> logging.Logger:
    """设置日志系统"""
    log_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = log_dir / f"build_index_{timestamp}.log"

    # 配置日志格式
    formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # 文件处理器
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.DEBUG)

    # 控制台处理器
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.setLevel(logging.INFO)

    # 配置根logger
    logger = logging.getLogger('build_index')
    logger.setLevel(logging.DEBUG)
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger, log_file


def print_section(title: str, logger: logging.Logger):
    """打印分隔线"""
    separator = "=" * 80
    logger.info("")
    logger.info(separator)
    logger.info(f"  {title}")
    logger.info(separator)


def print_subsection(title: str, logger: logging.Logger):
    """打印子标题"""
    logger.info(f"\n--- {title} ---")


def main():
    # 解析命令行参数
    parser = argparse.ArgumentParser(
        description='LargeRAG 向量索引构建工具',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例用法:
  # 构建生产环境索引（7000篇文献）
  python build_index.py --literature-dir data/literature_production --collection-name des_production_v1

  # 快速测试（35篇文献）
  python build_index.py --literature-dir data/literature --collection-name des_test_v1

  # 强制重建索引
  python build_index.py --literature-dir data/literature --rebuild

  # 禁用缓存（测试配置变化时推荐）
  python build_index.py --literature-dir data/literature --rebuild --no-cache

  # 覆盖文档处理配置
  python build_index.py --literature-dir data/literature --chunk-size 1024 --chunk-overlap 100
  python build_index.py --literature-dir data/literature --splitter-type semantic

  # 自定义向量存储配置
  python build_index.py --literature-dir data/literature --collection-name test_v2 --distance-metric l2
        """
    )

    # 必需参数
    parser.add_argument('--literature-dir', type=str, required=True, metavar='PATH',
                       help='文献目录路径（必需）')

    # 基本选项
    parser.add_argument('--rebuild', action='store_true',
                       help='强制重建索引（即使已存在）')
    parser.add_argument('--no-cache', action='store_true',
                       help='禁用缓存（确保使用最新配置重建）')

    # 文档处理配置
    doc_group = parser.add_argument_group('文档处理配置')
    doc_group.add_argument('--splitter-type', type=str, metavar='TYPE',
                          choices=['token', 'semantic', 'sentence'],
                          help='分块策略: token/semantic/sentence（默认: token）')
    doc_group.add_argument('--chunk-size', type=int, metavar='N',
                          help='文档分块大小（默认: 512）')
    doc_group.add_argument('--chunk-overlap', type=int, metavar='N',
                          help='文档分块重叠大小（默认: 50）')
    doc_group.add_argument('--separator', type=str, metavar='STR',
                          help='分块分隔符（默认: \\n\\n）')
    doc_group.add_argument('--semantic-breakpoint-threshold', type=float, metavar='FLOAT',
                          help='语义断点阈值 0-1（默认: 0.5 → 50%%，值越高越保守，仅semantic模式）')
    doc_group.add_argument('--semantic-buffer-size', type=int, metavar='N',
                          help='语义缓冲区大小（默认: 1，仅semantic模式）')
    doc_group.add_argument('--aggregate-small-chunks', action='store_true',
                          help='聚合JSON文件内的所有片段为一个Document（默认: false）')

    # 向量存储配置
    vector_group = parser.add_argument_group('向量存储配置')
    vector_group.add_argument('--collection-name', type=str, metavar='NAME',
                             help='集合名称（默认: des_literature_v1）')
    vector_group.add_argument('--distance-metric', type=str, metavar='METRIC',
                             choices=['cosine', 'l2', 'ip'],
                             help='距离度量: cosine/l2/ip（默认: cosine）')

    args = parser.parse_args()

    # 设置日志系统
    log_dir = Path(__file__).parent / "logs"
    logger, log_file = setup_logging(log_dir)

    print_section("LargeRAG 向量索引构建工具", logger)
    logger.info(f"日志文件: {log_file}")

    # ============================================================
    # 应用命令行参数覆盖到 SETTINGS
    # ============================================================
    overrides_applied = []

    # 缓存配置
    if args.no_cache:
        SETTINGS.cache.enabled = False
        overrides_applied.append(f"cache.enabled = False")

    # 文档处理配置
    if args.splitter_type is not None:
        SETTINGS.document_processing.splitter_type = args.splitter_type
        overrides_applied.append(f"document_processing.splitter_type = {args.splitter_type}")

    if args.chunk_size is not None:
        SETTINGS.document_processing.chunk_size = args.chunk_size
        overrides_applied.append(f"document_processing.chunk_size = {args.chunk_size}")

    if args.chunk_overlap is not None:
        SETTINGS.document_processing.chunk_overlap = args.chunk_overlap
        overrides_applied.append(f"document_processing.chunk_overlap = {args.chunk_overlap}")

    if args.separator is not None:
        SETTINGS.document_processing.separator = args.separator
        overrides_applied.append(f"document_processing.separator = {args.separator}")

    if args.semantic_breakpoint_threshold is not None:
        SETTINGS.document_processing.semantic_breakpoint_threshold = args.semantic_breakpoint_threshold
        overrides_applied.append(f"document_processing.semantic_breakpoint_threshold = {args.semantic_breakpoint_threshold}")

    if args.semantic_buffer_size is not None:
        SETTINGS.document_processing.semantic_buffer_size = args.semantic_buffer_size
        overrides_applied.append(f"document_processing.semantic_buffer_size = {args.semantic_buffer_size}")

    if args.aggregate_small_chunks:
        SETTINGS.document_processing.aggregate_small_chunks = True
        overrides_applied.append(f"document_processing.aggregate_small_chunks = True")

    # 向量存储配置
    if args.collection_name is not None:
        SETTINGS.vector_store.collection_name = args.collection_name
        overrides_applied.append(f"vector_store.collection_name = {args.collection_name}")

    if args.distance_metric is not None:
        SETTINGS.vector_store.distance_metric = args.distance_metric
        overrides_applied.append(f"vector_store.distance_metric = {args.distance_metric}")

    # 显示参数覆盖信息
    if overrides_applied:
        logger.info("\n⚙️  检测到命令行参数覆盖:")
        for override in overrides_applied:
            logger.info(f"  ✓ {override}")
        logger.info("")

    # ============================================================
    # 1. 验证文献目录
    # ============================================================
    print_section("步骤 1: 验证文献目录", logger)

    literature_dir = Path(args.literature_dir)

    if not literature_dir.exists():
        logger.error(f"✗ 错误: 文献目录不存在: {literature_dir}")
        return False

    if not literature_dir.is_dir():
        logger.error(f"✗ 错误: 路径不是目录: {literature_dir}")
        return False

    # 统计文献数量
    literature_folders = [d for d in literature_dir.iterdir() if d.is_dir()]
    num_papers = len(literature_folders)

    logger.info(f"\n文献目录: {literature_dir}")
    logger.info(f"✓ 检测到 {num_papers} 个文献文件夹")

    if num_papers == 0:
        logger.warning("⚠️  警告: 文献目录为空")
        return False

    # ============================================================
    # 2. 初始化 LargeRAG
    # ============================================================
    print_section("步骤 2: 初始化 LargeRAG", logger)

    collection_name = SETTINGS.vector_store.collection_name
    logger.info(f"\nCollection 名称: {collection_name}")
    logger.info("(独立的 collection，不会影响其他已有索引)")

    start_time = time.time()
    rag = LargeRAG(collection_name=collection_name)
    init_time = time.time() - start_time

    logger.info(f"\n✓ LargeRAG 初始化完成 (耗时: {init_time:.2f}秒)")

    # 显示当前配置
    logger.info(f"\n当前配置参数:")
    logger.info(f"  - Embedding模型:  {SETTINGS.embedding.model}")
    logger.info(f"  - 批处理大小:     {SETTINGS.embedding.batch_size}")
    logger.info(f"  - 向量维度:       {SETTINGS.embedding.dimension}")
    logger.info(f"  - 分块策略:       {SETTINGS.document_processing.splitter_type}")
    logger.info(f"  - 分块大小:       {SETTINGS.document_processing.chunk_size}")
    logger.info(f"  - 分块重叠:       {SETTINGS.document_processing.chunk_overlap}")
    logger.info(f"  - 缓存启用:       {SETTINGS.cache.enabled}")
    logger.info(f"  - 缓存类型:       {SETTINGS.cache.type}")

    # ============================================================
    # 3. 构建索引（或加载已有索引）
    # ============================================================
    print_section("步骤 3: 构建/加载索引", logger)

    # 检查是否需要重建索引
    need_rebuild = args.rebuild

    if not need_rebuild and rag.query_engine is not None:
        # 有索引，检查是否为空
        stats_temp = rag.get_stats()
        index_count = stats_temp['index_stats'].get('document_count', 0)
        if index_count == 0:
            logger.warning("\n⚠️  检测到索引为空（可能之前构建失败），将强制重建...")
            need_rebuild = True
        else:
            logger.info(f"\n✓ 检测到已有索引（{index_count:,} 个节点），跳过构建步骤")
            logger.info("  提示: 使用 --rebuild 参数可强制重建索引")

    if need_rebuild or rag.query_engine is None:
        if need_rebuild:
            logger.info("\n🔄 强制重建索引...")
        else:
            logger.info("\n未检测到已有索引，开始构建...")

        logger.info(f"文献数量: {num_papers}")
        logger.info(f"文献目录: {literature_dir}")

        if num_papers > 1000:
            logger.info(f"\n⚠️  注意: 文献数量较大（{num_papers}篇），预计需要较长时间")
            logger.info("  - 预估时间: 根据API限额而定，可能需要数小时")
            logger.info("  - 支持断点续传: 如果中断，重新运行相同命令即可继续")
            logger.info("  - 缓存机制: 已处理的文档会缓存，不会重复调用API\n")

        logger.info("开始构建索引...\n")

        start_time = time.time()
        success = rag.index_from_folders(str(literature_dir))
        index_time = time.time() - start_time

        if not success:
            logger.error("\n✗ 索引构建失败")
            return False

        logger.info(f"\n✓ 索引构建成功 (总耗时: {index_time:.2f}秒 / {index_time/60:.2f}分钟)")

    # ============================================================
    # 4. 显示索引统计信息
    # ============================================================
    print_section("步骤 4: 索引统计信息", logger)

    stats = rag.get_stats()
    index_stats = stats['index_stats']
    doc_stats = stats['doc_processing_stats']

    logger.info(f"\n📊 向量索引统计:")
    logger.info(f"  Collection:      {index_stats.get('collection_name', 'N/A')}")
    logger.info(f"  索引节点数:      {index_stats.get('document_count', 0):,}")
    logger.info(f"  存储位置:        {index_stats.get('persist_directory', 'N/A')}")

    logger.info(f"\n📊 文档处理统计:")
    processed = doc_stats.get('processed', 0)
    skipped = doc_stats.get('skipped', 0)
    total = doc_stats.get('total', 0)

    logger.info(f"  已处理文档段落: {processed:,}")
    logger.info(f"  跳过文档:        {skipped:,}")
    logger.info(f"  总计:            {total:,}")

    if total > 0:
        success_rate = (processed / total) * 100
        logger.info(f"  成功率:          {success_rate:.2f}%")

    # ============================================================
    # 5. 保存构建报告
    # ============================================================
    print_section("步骤 5: 保存构建报告", logger)

    # 创建输出目录
    output_dir = Path(__file__).parent / "build_reports"
    output_dir.mkdir(exist_ok=True)

    # 生成文件名（带时间戳）
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_file = output_dir / f"build_report_{collection_name}_{timestamp}.json"

    # 整合所有结果
    build_report = {
        "build_info": {
            "timestamp": timestamp,
            "literature_dir": str(literature_dir),
            "collection_name": collection_name,
            "num_literature": num_papers,
            "rebuild": args.rebuild,
            "cache_enabled": SETTINGS.cache.enabled,
        },
        "config_parameters": asdict(SETTINGS),
        "index_stats": index_stats,
        "doc_processing_stats": doc_stats,
    }

    # 保存到 JSON
    with open(report_file, 'w', encoding='utf-8') as f:
        json.dump(build_report, f, ensure_ascii=False, indent=2)

    logger.info(f"\n✓ 构建报告已保存到: {report_file}")

    # ============================================================
    # 6. 完成
    # ============================================================
    print_section("构建完成！", logger)

    logger.info("\n✅ 向量索引构建完成")
    logger.info(f"\n索引信息:")
    logger.info(f"  Collection:  {collection_name}")
    logger.info(f"  节点数:      {index_stats.get('document_count', 0):,}")
    logger.info(f"  文献数:      {num_papers}")

    logger.info(f"\n数据文件位置:")
    logger.info(f"  向量数据库:  {index_stats.get('persist_directory', 'N/A')}")
    logger.info(f"  日志文件:    {log_file}")
    logger.info(f"  构建报告:    {report_file}")

    logger.info("\n下一步操作:")
    logger.info("  1. 验证索引:")
    logger.info(f"     python -c \"from largerag import LargeRAG; rag=LargeRAG(collection_name='{collection_name}'); print(rag.get_stats())\"")
    logger.info("\n  2. 测试查询:")
    logger.info("     python examples/2_query_and_retrieve.py")
    logger.info("\n  3. 部署到服务器:")
    logger.info(f"     复制 {index_stats.get('persist_directory', 'N/A')} 到服务器")

    logger.info("\n" + "=" * 80 + "\n")

    return True


if __name__ == "__main__":
    try:
        success = main()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n⚠️  用户中断构建")
        print("提示: 重新运行相同命令可继续构建（缓存会保留已处理的文档）")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 构建失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
