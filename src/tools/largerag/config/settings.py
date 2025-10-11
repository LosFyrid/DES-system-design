"""
配置加载器
要求：
1. 支持 ${PROJECT_ROOT} 变量替换
2. 支持 {{key}} 内部引用
3. 从 .env 读取 DASHSCOPE_API_KEY
4. 提供类型安全的配置对象
"""

import os
import re
import yaml
from pathlib import Path
from dataclasses import dataclass
from typing import Optional
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# ============ YAML 变量替换正则 ============
path_matcher = re.compile(r'\$\{([^}^{]+)\}')
key_matcher = re.compile(r'\{\{([^}^{]+)\}\}')


def path_constructor(loader, node):
    """处理 ${ENV_VAR} 变量替换"""
    value = node.value
    match = path_matcher.match(value)
    env_var = match.group()[2:-1]
    project_root = os.environ.get(env_var, '')
    return os.path.join(project_root, value[match.end():])


def resolve_key_references(yaml_dict):
    """处理 {{key}} 内部引用"""
    def _resolve_value(value, current_level_dict):
        if isinstance(value, str):
            match = key_matcher.search(value)
            if match:
                key = match.group(1).strip()
                if key in current_level_dict:
                    return value.replace(match.group(0), str(current_level_dict[key]))
                elif key in yaml_dict:
                    return value.replace(match.group(0), str(yaml_dict[key]))
        return value

    resolved_dict = {}
    for key, value in yaml_dict.items():
        if isinstance(value, dict):
            resolved_dict[key] = resolve_key_references(value)
        else:
            resolved_dict[key] = _resolve_value(value, yaml_dict)
    return resolved_dict


# 注册 YAML 解析器
yaml.SafeLoader.add_implicit_resolver('!path', path_matcher, None)
yaml.SafeLoader.add_constructor('!path', path_constructor)


# ============ 配置数据类 ============
@dataclass
class EmbeddingConfig:
    provider: str
    model: str
    text_type: str
    batch_size: int
    dimension: int


@dataclass
class VectorStoreConfig:
    type: str
    persist_directory: str
    collection_name: str
    distance_metric: str


@dataclass
class DocumentProcessingConfig:
    chunk_size: int
    chunk_overlap: int
    separator: str


@dataclass
class RetrievalConfig:
    similarity_top_k: int
    rerank_top_n: int
    similarity_threshold: float


@dataclass
class RerankerConfig:
    provider: str
    model: str
    enabled: bool


@dataclass
class LLMConfig:
    provider: str
    model: str
    temperature: float
    max_tokens: int


@dataclass
class CacheConfig:
    enabled: bool
    type: str
    redis_host: str
    redis_port: int
    redis_db: int
    collection_name: str
    ttl: int


@dataclass
class LoggingConfig:
    level: str
    file_path: str
    format: str


@dataclass
class LargeRAGSettings:
    embedding: EmbeddingConfig
    vector_store: VectorStoreConfig
    document_processing: DocumentProcessingConfig
    retrieval: RetrievalConfig
    reranker: RerankerConfig
    llm: LLMConfig
    cache: CacheConfig
    logging: LoggingConfig


# ============ 配置加载 ============
def load_settings(config_path: Optional[str] = None) -> LargeRAGSettings:
    """加载配置文件"""
    if config_path is None:
        config_path = Path(__file__).parent / "settings.yaml"

    with open(config_path, 'r', encoding='utf-8') as f:
        yaml_data = yaml.safe_load(f)

    # 设置 PROJECT_ROOT（如果未设置）
    if 'PROJECT_ROOT' not in os.environ:
        # 自动推断项目根目录（向上查找 .git 目录）
        current = Path(__file__).parent
        while current != current.parent:
            if (current / '.git').exists():
                os.environ['PROJECT_ROOT'] = str(current) + os.sep
                break
            current = current.parent

    # 变量替换
    resolved = resolve_key_references(yaml_data)

    # 手动替换 ${PROJECT_ROOT}（因为 path_constructor 只处理 YAML 加载时的值）
    def replace_project_root(d):
        if isinstance(d, dict):
            return {k: replace_project_root(v) for k, v in d.items()}
        elif isinstance(d, str):
            project_root = os.environ.get('PROJECT_ROOT', '')
            return d.replace('${PROJECT_ROOT}', project_root)
        else:
            return d

    resolved = replace_project_root(resolved)

    # 构建配置对象
    settings = LargeRAGSettings(
        embedding=EmbeddingConfig(**resolved['embedding']),
        vector_store=VectorStoreConfig(**resolved['vector_store']),
        document_processing=DocumentProcessingConfig(**resolved['document_processing']),
        retrieval=RetrievalConfig(**resolved['retrieval']),
        reranker=RerankerConfig(**resolved['reranker']),
        llm=LLMConfig(**resolved['llm']),
        cache=CacheConfig(**resolved['cache']),
        logging=LoggingConfig(**resolved['logging']),
    )

    return settings


# ============ API Key 获取 ============
def get_dashscope_api_key() -> str:
    """从环境变量获取 DashScope API Key"""
    api_key = os.getenv("DASHSCOPE_API_KEY")
    if not api_key:
        raise ValueError(
            "DASHSCOPE_API_KEY not found in environment variables. "
            "Please add it to .env file."
        )
    return api_key


# ============ 全局配置实例 ============
SETTINGS = load_settings()

# 尝试获取 API Key（但不在模块导入时失败，只是警告）
try:
    DASHSCOPE_API_KEY = get_dashscope_api_key()
except ValueError as e:
    DASHSCOPE_API_KEY = None
    print(f"Warning: {e}")
