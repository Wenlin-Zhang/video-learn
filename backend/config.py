"""配置管理模块"""
import os
from pathlib import Path
from typing import Optional, List

import yaml
from pydantic import BaseModel


class ASRConfig(BaseModel):
    """ASR模型配置"""
    model: str = "Qwen/Qwen3-ASR-0.6B"
    aligner_model: str = "Qwen/Qwen3-ForcedAligner-0.6B"
    backend: str = "vllm"  # "vllm" 或 "transformers"
    gpu_memory_utilization: float = 0.7  # vLLM GPU显存利用率
    max_inference_batch_size: int = 32  # 推理批处理大小
    max_new_tokens: int = 2048  # 最大生成token数
    use_flash_attention: bool = True  # 是否使用FlashAttention
    language: str = "Chinese"  # 默认语言
    hotwords: List[str] = []  # 热词列表，用于上下文注入提高识别准确率
    extract_hotwords_from_filename: bool = True  # 是否从文件名自动提取热词


class LLMConfig(BaseModel):
    """LLM API配置"""
    api_base: str = "https://api.openai.com/v1"
    api_key: str = ""
    model: str = "qwen3"


class StorageConfig(BaseModel):
    """存储配置"""
    upload_dir: str = "./uploads"
    output_dir: str = "./outputs"


class AppConfig(BaseModel):
    """应用配置"""
    asr: ASRConfig = ASRConfig()
    llm: LLMConfig = LLMConfig()
    storage: StorageConfig = StorageConfig()


# 全局配置实例
_config: Optional[AppConfig] = None


def get_config_path() -> Path:
    """获取配置文件路径"""
    return Path(__file__).parent / "config.yaml"


def load_config() -> AppConfig:
    """加载配置文件"""
    global _config
    if _config is not None:
        return _config
    
    config_path = get_config_path()
    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
            _config = AppConfig(**data) if data else AppConfig()
    else:
        _config = AppConfig()
        # 创建默认配置文件
        save_config(_config)
    
    # 从环境变量覆盖敏感配置
    if env_api_key := os.environ.get("LLM_API_KEY"):
        _config.llm.api_key = env_api_key
    if env_api_base := os.environ.get("LLM_API_BASE"):
        _config.llm.api_base = env_api_base
    
    # 确保目录存在
    Path(_config.storage.upload_dir).mkdir(parents=True, exist_ok=True)
    Path(_config.storage.output_dir).mkdir(parents=True, exist_ok=True)
    
    return _config


def save_config(config: AppConfig) -> None:
    """保存配置到文件"""
    config_path = get_config_path()
    with open(config_path, "w", encoding="utf-8") as f:
        yaml.dump(config.model_dump(), f, allow_unicode=True, default_flow_style=False)


def get_config() -> AppConfig:
    """获取配置实例"""
    global _config
    if _config is None:
        return load_config()
    return _config
