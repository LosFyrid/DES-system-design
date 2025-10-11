"""
LargeRAG 主接口类
要求：
1. 简洁的 API 设计，供 Reasoning Agent 调用
2. 自动处理初始化和资源管理
3. 提供清晰的错误提示
"""

from typing import List, Dict, Any, Optional
from pathlib import Path
import logging

from core.document_processor import DocumentProcessor
from core.indexer import LargeRAGIndexer
from core.query_engine import LargeRAGQueryEngine
from config.settings import SETTINGS

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class LargeRAG:
    """
    LargeRAG 主接口类

    使用示例：
        # 1. 初始化
        rag = LargeRAG()

        # 2. 索引文档（首次运行）
        rag.index_from_folders("src/tools/largerag/data/literature")

        # 3. 查询（后续运行可直接查询，自动加载索引）
        answer = rag.query("如何设计低温 DES 溶剂？")
        print(answer)
    """

    def __init__(self, config_path: Optional[str] = None):
        """
        初始化 LargeRAG

        Args:
            config_path: 配置文件路径（可选，默认使用 config/settings.yaml）
        """
        logger.info("Initializing LargeRAG...")

        self.doc_processor = DocumentProcessor()
        self.indexer = LargeRAGIndexer()
        self.query_engine = None

        # 尝试加载已有索引
        index = self.indexer.load_index()
        if index:
            self.query_engine = LargeRAGQueryEngine(index)
            logger.info("Loaded existing index")
        else:
            logger.warning("No existing index found. Please run index_from_folders() first.")

    def index_from_folders(self, literature_dir: str) -> bool:
        """
        从文献文件夹结构构建索引

        Args:
            literature_dir: 文献目录路径（如 "src/tools/largerag/data/literature"）

        Returns:
            bool: 是否成功

        注意：
        - 如果索引已存在，将覆盖旧索引
        - 使用缓存，重复运行时只计算新增文档的 embedding
        """
        try:
            logger.info(f"Starting indexing process from {literature_dir}...")

            # 1. 处理文档
            documents = self.doc_processor.process_from_folders(literature_dir)
            stats = self.doc_processor.get_statistics()
            logger.info(f"Document processing stats: {stats}")

            if not documents:
                logger.error("No valid documents to index")
                return False

            # 2. 构建索引
            index = self.indexer.build_index(documents)

            # 3. 初始化查询引擎
            self.query_engine = LargeRAGQueryEngine(index)

            logger.info("Indexing completed successfully")
            return True

        except Exception as e:
            logger.error(f"Indexing failed: {e}", exc_info=True)
            return False

    def query(self, query_text: str, **kwargs) -> str:
        """
        执行查询并生成回答

        Args:
            query_text: 查询文本
            **kwargs: 自定义参数

        Returns:
            LLM 生成的回答

        Raises:
            RuntimeError: 如果索引未初始化
        """
        if self.query_engine is None:
            raise RuntimeError(
                "Index not initialized. Please run index_from_folders() first."
            )

        return self.query_engine.query(query_text, **kwargs)

    def get_similar_docs(
        self,
        query_text: str,
        top_k: int = 5
    ) -> List[Dict[str, Any]]:
        """
        获取相似文档（不生成回答）

        Args:
            query_text: 查询文本
            top_k: 返回数量

        Returns:
            文档列表
        """
        if self.query_engine is None:
            raise RuntimeError(
                "Index not initialized. Please run index_from_folders() first."
            )

        return self.query_engine.get_similar_documents(query_text, top_k)

    def get_stats(self) -> Dict[str, Any]:
        """获取系统统计信息"""
        return {
            "index_stats": self.indexer.get_index_stats(),
            "doc_processing_stats": self.doc_processor.get_statistics(),
        }
