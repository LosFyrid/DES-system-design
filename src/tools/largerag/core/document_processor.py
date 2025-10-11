"""
文档处理器模块
要求：
1. 支持从文件夹结构加载文献数据
2. 优先使用 content_list_process.json（只提取 text 类型）
3. 自动提取元数据（文档哈希、页码、文本层级）
4. 处理缺失字段和异常文件
5. 记录处理日志（跳过的文档、错误）
"""

from typing import List, Dict, Any
from pathlib import Path
import json
import logging
from llama_index.core import Document

logger = logging.getLogger(__name__)


class DocumentProcessor:
    """文献文件夹到 LlamaIndex Document 的转换器"""

    def __init__(self):
        self.processed_count = 0
        self.skipped_count = 0

    def process_from_folders(self, literature_dir: str) -> List[Document]:
        """
        从文献文件夹结构加载数据并转换为 Document 对象

        文件夹结构：
            data/literature/
            ├── {hash1}/
            │   ├── content_list_process.json  # 优先使用（处理后的内容）
            │   ├── article.json               # 备选（段落级数据）
            │   ├── {hash1}.md                 # 不使用（全文 markdown）
            │   └── images/                    # 不处理
            └── {hash2}/
                └── ...

        Args:
            literature_dir: 文献目录路径（如 "data/literature"）

        Returns:
            Document 对象列表（仅包含文本内容）

        Raises:
            FileNotFoundError: 如果目录不存在
        """
        literature_path = Path(literature_dir)
        if not literature_path.exists():
            raise FileNotFoundError(f"Literature directory not found: {literature_dir}")

        documents = []

        # 遍历所有哈希文件夹
        for folder in literature_path.iterdir():
            if not folder.is_dir():
                continue

            doc_hash = folder.name
            content_file = folder / "content_list_process.json"
            article_file = folder / "article.json"

            # 优先使用 content_list_process.json
            if content_file.exists():
                docs = self._load_from_content_list(content_file, doc_hash)
                documents.extend(docs)
            elif article_file.exists():
                logger.warning(f"[{doc_hash}] content_list_process.json not found, using article.json")
                docs = self._load_from_article(article_file, doc_hash)
                documents.extend(docs)
            else:
                logger.error(f"[{doc_hash}] No valid JSON file found, skipping")
                self.skipped_count += 1

        logger.info(f"Total processed: {self.processed_count}, skipped: {self.skipped_count}")
        return documents

    def _load_from_content_list(self, file_path: Path, doc_hash: str) -> List[Document]:
        """
        从 content_list_process.json 加载数据（只提取 text 类型）

        JSON 格式：
        [
            {
                "type": "text",
                "text": "Deep eutectic solvents...",
                "text_level": 1,
                "page_idx": 0,
                "cites": [...]  # 可选
            },
            {
                "type": "image",  # 忽略
                ...
            }
        ]
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content_list = json.load(f)

            documents = []
            for idx, item in enumerate(content_list):
                # 只处理 text 类型
                if item.get("type") != "text":
                    continue

                text = item.get("text", "").strip()
                if not text:
                    logger.warning(f"[{doc_hash}] Item {idx}: empty text, skipping")
                    continue

                # 提取元数据
                metadata = {
                    "doc_hash": doc_hash,
                    "page_idx": item.get("page_idx", -1),
                    "text_level": item.get("text_level", 0),
                    "has_citations": bool(item.get("cites")),
                    "source_file": "content_list_process.json",
                    "item_idx": idx,
                }

                doc = Document(text=text, metadata=metadata)
                documents.append(doc)
                self.processed_count += 1

            logger.info(f"[{doc_hash}] Loaded {len(documents)} text segments from content_list_process.json")
            return documents

        except json.JSONDecodeError as e:
            logger.error(f"[{doc_hash}] Invalid JSON in content_list_process.json: {e}")
            self.skipped_count += 1
            return []
        except Exception as e:
            logger.error(f"[{doc_hash}] Error loading content_list_process.json: {e}")
            self.skipped_count += 1
            return []

    def _load_from_article(self, file_path: Path, doc_hash: str) -> List[Document]:
        """
        从 article.json 加载数据（备选方案）

        JSON 格式：
        {
            "paragraphs": [
                {
                    "paragraph": "Dissolution of...",
                    "type": "body_div",
                    "paragraph_idx": 0,
                    "pagenum": 0,
                    "head": "",
                    "text_level": 1
                }
            ]
        }
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                article_data = json.load(f)

            paragraphs = article_data.get("paragraphs", [])
            documents = []

            for para in paragraphs:
                text = para.get("paragraph", "").strip()
                if not text:
                    continue

                metadata = {
                    "doc_hash": doc_hash,
                    "page_idx": para.get("pagenum", -1),
                    "text_level": para.get("text_level", 0),
                    "paragraph_type": para.get("type", ""),
                    "source_file": "article.json",
                    "paragraph_idx": para.get("paragraph_idx", -1),
                }

                doc = Document(text=text, metadata=metadata)
                documents.append(doc)
                self.processed_count += 1

            logger.info(f"[{doc_hash}] Loaded {len(documents)} paragraphs from article.json")
            return documents

        except json.JSONDecodeError as e:
            logger.error(f"[{doc_hash}] Invalid JSON in article.json: {e}")
            self.skipped_count += 1
            return []
        except Exception as e:
            logger.error(f"[{doc_hash}] Error loading article.json: {e}")
            self.skipped_count += 1
            return []

    def get_statistics(self) -> Dict[str, int]:
        """返回处理统计信息"""
        return {
            "processed": self.processed_count,
            "skipped": self.skipped_count,
            "total": self.processed_count + self.skipped_count
        }
