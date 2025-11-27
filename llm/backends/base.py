"""
LLM Backend 抽象基类
定义所有后端必须实现的接口
"""
from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any


class BaseLLMBackend(ABC):
    """LLM后端抽象基类"""

    def __init__(self, **config):
        """
        初始化后端

        Args:
            **config: 后端特定的配置参数
        """
        self.config = config

    @abstractmethod
    def is_available(self) -> bool:
        """
        检查后端是否可用

        Returns:
            True if available, False otherwise
        """
        pass

    @abstractmethod
    def chat_completion(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.3,
        max_tokens: int = 2000,
        timeout: int = 180,
        **kwargs
    ) -> Optional[str]:
        """
        执行对话补全

        Args:
            messages: 消息列表 [{"role": "system/user/assistant", "content": "..."}]
            temperature: 温度参数 (0.0-1.0)
            max_tokens: 最大生成token数
            timeout: 超时时间（秒）
            **kwargs: 其他后端特定参数

        Returns:
            生成的文本，失败返回None
        """
        pass

    @abstractmethod
    def get_backend_name(self) -> str:
        """
        获取后端名称

        Returns:
            后端名称字符串
        """
        pass
