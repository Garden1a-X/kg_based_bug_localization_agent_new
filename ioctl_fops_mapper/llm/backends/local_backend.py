"""
本地服务器后端实现（预留）
用于直接调用本地部署的模型，而不通过 OpenAI API
"""
from typing import Optional, List, Dict
from loguru import logger
from .base import BaseLLMBackend


class LocalServerBackend(BaseLLMBackend):
    """本地服务器后端（预留，未来实现）"""

    def __init__(
        self,
        server_url: str = "http://localhost:8000",
        model: str = "local-model",
        **kwargs
    ):
        """
        初始化本地服务器后端

        Args:
            server_url: 本地服务器地址
            model: 模型名称
            **kwargs: 其他配置
        """
        super().__init__(server_url=server_url, model=model, **kwargs)

        self.server_url = server_url
        self.model = model

        logger.warning("LocalServerBackend 尚未实现，请使用 OpenAIBackend")

    def is_available(self) -> bool:
        """检查后端是否可用"""
        return False  # 未实现

    def chat_completion(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.3,
        max_tokens: int = 2000,
        timeout: int = 180,
        **kwargs
    ) -> Optional[str]:
        """
        执行对话补全（未实现）

        Args:
            messages: 消息列表
            temperature: 温度参数
            max_tokens: 最大token数
            timeout: 超时时间
            **kwargs: 其他参数

        Returns:
            生成的文本
        """
        logger.error("LocalServerBackend 尚未实现")
        return None

    def get_backend_name(self) -> str:
        """获取后端名称"""
        return f"LocalServer ({self.model})"


# TODO: 未来可以添加其他后端，例如：
# - HuggingFaceBackend: 使用 transformers 库直接加载模型
# - VLLMBackend: 使用 vLLM 专有 API
# - ClaudeBackend: 使用 Anthropic Claude API
# - GeminiBackend: 使用 Google Gemini API
