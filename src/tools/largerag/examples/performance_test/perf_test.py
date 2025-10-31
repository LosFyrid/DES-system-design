"""
LargeRAG 性能测试脚本
====================================

测试内容：
1. 对 rag_performance_test 文件夹中的10篇文献建立索引
2. 使用 question.txt 中的10个问题测试RAG性能
3. 记录每个问题的答案、检索性能和LLM生成质量

运行方式：
    python examples/performance_test/perf_test.py              # 正常运行（加载已有索引）
    python examples/performance_test/perf_test.py --rebuild    # 强制重建索引

数据结构：
    src/tools/largerag/data/rag_performance_test/
    ├── 1/ ... 10/  (10篇文献文件夹)
    └── question.txt (10个测试问题)
"""

import sys
import time
import json
import argparse
from pathlib import Path
from datetime import datetime

# 添加项目根目录到sys.path
# perf_test.py → performance_test → examples → largerag → tools → src → PROJECT_ROOT
project_root = Path(__file__).resolve().parents[5]  # 往上5级
sys.path.insert(0, str(project_root))

from src.tools.largerag import LargeRAG
from src.tools.largerag.config.settings import SETTINGS


def print_section(title: str):
    """打印分隔线"""
    print("\n" + "=" * 80)
    print(f"  {title}")
    print("=" * 80)


def print_subsection(title: str):
    """打印子标题"""
    print(f"\n--- {title} ---")


def main():
    # 解析命令行参数
    parser = argparse.ArgumentParser(description='LargeRAG 性能测试')
    parser.add_argument('--rebuild', action='store_true',
                       help='强制重建索引（即使已存在）')
    args = parser.parse_args()

    print_section("LargeRAG 性能测试 - 10篇文献 + 10个问题")

    # ============================================================
    # 1. 设置测试参数
    # ============================================================
    print_section("步骤 1: 初始化测试环境")

    # 测试数据路径
    test_data_dir = Path(__file__).parent.parent.parent / "data" / "rag_performance_test"
    question_file = test_data_dir / "question.txt"

    # 自定义 collection 名称（避免与其他索引混淆）
    collection_name = "rag_perf_test_10papers"

    print(f"\n测试数据目录: {test_data_dir}")
    print(f"问题文件: {question_file}")
    print(f"Collection 名称: {collection_name}")

    # 检查测试数据是否存在
    if not test_data_dir.exists():
        print(f"\n✗ 错误: 测试数据目录不存在: {test_data_dir}")
        return False

    if not question_file.exists():
        print(f"\n✗ 错误: 问题文件不存在: {question_file}")
        return False

    # 统计文献数量
    literature_folders = [d for d in test_data_dir.iterdir() if d.is_dir()]
    print(f"\n✓ 检测到 {len(literature_folders)} 个文献文件夹")

    # ============================================================
    # 2. 初始化 LargeRAG（使用自定义 collection）
    # ============================================================
    print_section("步骤 2: 初始化 LargeRAG")

    print(f"\n使用自定义 collection: {collection_name}")
    print("(这样不会影响其他已有的索引)")

    start_time = time.time()
    rag = LargeRAG(collection_name=collection_name)
    init_time = time.time() - start_time

    print(f"\n✓ LargeRAG 初始化完成 (耗时: {init_time:.2f}秒)")

    # 获取当前配置参数（用于测试）
    retrieval_top_k = SETTINGS.retrieval.rerank_top_n  # 最终返回给用户的文档数
    print(f"\n当前配置参数:")
    print(f"  - 向量检索召回数: {SETTINGS.retrieval.similarity_top_k}")
    print(f"  - Reranker返回数: {SETTINGS.retrieval.rerank_top_n}")
    print(f"  - Reranker启用:   {SETTINGS.reranker.enabled}")
    print(f"  - LLM模型:        {SETTINGS.llm.model}")
    print(f"  - 温度:           {SETTINGS.llm.temperature}")
    print(f"  - 最大tokens:     {SETTINGS.llm.max_tokens}")

    # ============================================================
    # 3. 构建索引（或加载已有索引）
    # ============================================================
    print_section("步骤 3: 构建/加载索引")

    # 检查是否需要重建索引
    need_rebuild = args.rebuild  # 用户明确要求重建

    if not need_rebuild and rag.query_engine is not None:
        # 有索引，检查是否为空
        stats_temp = rag.get_stats()
        index_count = stats_temp['index_stats'].get('document_count', 0)
        if index_count == 0:
            print("\n⚠️  检测到索引为空（可能之前构建失败），将强制重建...")
            need_rebuild = True
        else:
            print(f"\n✓ 检测到已有索引（{index_count} 个节点），跳过构建步骤")
            print("  提示: 使用 --rebuild 参数可强制重建索引")

    if need_rebuild or rag.query_engine is None:
        if need_rebuild:
            print("\n🔄 强制重建索引...")
        else:
            print("\n未检测到已有索引，开始构建...")

        print(f"文献数量: {len(literature_folders)}")

        start_time = time.time()
        success = rag.index_from_folders(str(test_data_dir))
        index_time = time.time() - start_time

        if not success:
            print("\n✗ 索引构建失败")
            return False

        print(f"\n✓ 索引构建成功 (耗时: {index_time:.2f}秒 / {index_time/60:.2f}分钟)")

    # 显示索引统计信息
    stats = rag.get_stats()
    index_stats = stats['index_stats']
    doc_stats = stats['doc_processing_stats']

    print_subsection("索引统计信息")
    print(f"  Collection: {index_stats.get('collection_name', 'N/A')}")
    print(f"  索引节点数: {index_stats.get('document_count', 0)}")
    print(f"  处理文档数: {doc_stats.get('processed', 0)}")

    # ============================================================
    # 4. 读取测试问题
    # ============================================================
    print_section("步骤 4: 读取测试问题")

    with open(question_file, 'r', encoding='utf-8') as f:
        questions = [line.strip() for line in f.readlines() if line.strip()]

    print(f"\n✓ 读取到 {len(questions)} 个问题\n")

    for i, q in enumerate(questions, 1):
        print(f"  Q{i}: {q}")

    # ============================================================
    # 5. 执行测试 - 对每个问题进行查询
    # ============================================================
    print_section("步骤 5: 执行性能测试")

    results = []
    total_query_time = 0
    total_retrieval_time = 0

    print("\n开始测试...\n")

    for i, question in enumerate(questions, 1):
        print_subsection(f"问题 {i}/{len(questions)}")
        print(f"问题: {question}\n")

        # 5.1 检索相似文档（不使用LLM）
        print("  [1/2] 检索相似文档...")
        start_time = time.time()
        similar_docs = rag.get_similar_docs(question, top_k=retrieval_top_k)
        retrieval_time = time.time() - start_time
        total_retrieval_time += retrieval_time

        print(f"  ✓ 检索完成 (耗时: {retrieval_time:.2f}秒)")
        print(f"  检索到 {len(similar_docs)} 个相关文档")

        # 显示检索的文档分数
        if similar_docs:
            print(f"  相似度分数范围: {similar_docs[0]['score']:.4f} ~ {similar_docs[-1]['score']:.4f}")

        # 5.2 生成回答（使用LLM）
        print("\n  [2/2] 生成回答...")
        start_time = time.time()
        answer = rag.query(question)
        query_time = time.time() - start_time
        total_query_time += query_time

        print(f"  ✓ 回答生成完成 (耗时: {query_time:.2f}秒)")

        # 显示回答（前200字符）
        answer_preview = answer[:200] + "..." if len(answer) > 200 else answer
        print(f"\n  回答:\n  {answer_preview}\n")

        # 记录结果
        result = {
            "question_id": i,
            "question": question,
            "answer": answer,
            "retrieval_time_sec": round(retrieval_time, 2),
            "query_time_sec": round(query_time, 2),
            "num_retrieved_docs": len(similar_docs),
            "similarity_scores": [round(doc['score'], 4) for doc in similar_docs],
            "top_doc_sources": [
                {
                    "doc_hash": doc['metadata'].get('doc_hash', 'N/A')[:16],
                    "page_idx": doc['metadata'].get('page_idx', 'N/A'),
                    "score": round(doc['score'], 4)
                }
                for doc in similar_docs[:3]  # 只记录前3个文档来源
            ]
        }
        results.append(result)

    # ============================================================
    # 6. 统计测试结果
    # ============================================================
    print_section("步骤 6: 测试结果统计")

    avg_retrieval_time = total_retrieval_time / len(questions)
    avg_query_time = total_query_time / len(questions)

    print("\n📊 性能统计:")
    print(f"  总问题数:           {len(questions)}")
    print(f"  平均检索时间:       {avg_retrieval_time:.2f}秒")
    print(f"  平均查询时间:       {avg_query_time:.2f}秒")
    print(f"  总检索时间:         {total_retrieval_time:.2f}秒")
    print(f"  总查询时间:         {total_query_time:.2f}秒")

    print("\n📊 索引统计:")
    print(f"  文献数量:           {len(literature_folders)}")
    print(f"  索引节点数:         {index_stats.get('document_count', 0)}")
    print(f"  Collection:         {collection_name}")

    # ============================================================
    # 7. 保存测试结果到 JSON
    # ============================================================
    print_section("步骤 7: 保存测试结果")

    # 创建输出目录
    output_dir = Path(__file__).parent / "test_results"
    output_dir.mkdir(exist_ok=True)

    # 生成文件名（带时间戳）
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = output_dir / f"perf_test_{timestamp}.json"

    # 整合所有结果
    full_results = {
        "test_info": {
            "timestamp": timestamp,
            "test_data_dir": str(test_data_dir),
            "collection_name": collection_name,
            "num_literature": len(literature_folders),
            "num_questions": len(questions),
        },
        "config_parameters": {
            "similarity_top_k": SETTINGS.retrieval.similarity_top_k,
            "rerank_top_n": SETTINGS.retrieval.rerank_top_n,
            "similarity_threshold": SETTINGS.retrieval.similarity_threshold,
            "reranker_enabled": SETTINGS.reranker.enabled,
            "reranker_model": SETTINGS.reranker.model,
            "llm_model": SETTINGS.llm.model,
            "llm_temperature": SETTINGS.llm.temperature,
            "llm_max_tokens": SETTINGS.llm.max_tokens,
            "chunk_size": SETTINGS.document_processing.chunk_size,
            "chunk_overlap": SETTINGS.document_processing.chunk_overlap,
        },
        "performance_summary": {
            "avg_retrieval_time_sec": round(avg_retrieval_time, 2),
            "avg_query_time_sec": round(avg_query_time, 2),
            "total_retrieval_time_sec": round(total_retrieval_time, 2),
            "total_query_time_sec": round(total_query_time, 2),
        },
        "index_stats": index_stats,
        "questions_and_answers": results,
    }

    # 保存到 JSON
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(full_results, f, ensure_ascii=False, indent=2)

    print(f"\n✓ 测试结果已保存到: {output_file}")

    # ============================================================
    # 8. 完成
    # ============================================================
    print_section("测试完成！")

    print("\n✅ 所有测试已完成")
    print(f"\n测试结果文件: {output_file}")
    print("\n可以查看 JSON 文件获取详细结果，包括:")
    print("  - 每个问题的完整回答")
    print("  - 检索性能指标（时间、相似度分数）")
    print("  - 文档来源信息（doc_hash, page_idx）")

    print("\n" + "=" * 80 + "\n")

    return True


if __name__ == "__main__":
    try:
        success = main()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n⚠️  用户中断测试")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
