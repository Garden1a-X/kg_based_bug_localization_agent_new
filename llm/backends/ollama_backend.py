"""
Ollama Backend Implementation for LLM Client
支持本地部署的Ollama模型
"""
import logging
from typing import Dict, List, Optional
import requests
from .base import BaseLLMBackend

logger = logging.getLogger(__name__)


class OllamaBackend(BaseLLMBackend):
    """
    Ollama后端实现

    支持本地部署的Ollama模型，使用HTTP API进行通信
    """

    def __init__(
        self,
        host: str = "http://localhost:11434",
        model: str = "qwen3:4b-instruct-2507-fp16",
        timeout: int = 180,
        **kwargs
    ):
        """
        初始化Ollama后端

        Args:
            host: Ollama服务器地址（默认: http://localhost:11434）
            model: 模型名称（默认: qwen3:4b-instruct-2507-fp16）
            timeout: 请求超时时间（秒）
            **kwargs: 其他参数
        """
        self.host = host.rstrip('/')  # 移除末尾的斜杠
        self.model = model
        self.timeout = timeout
        self.chat_endpoint = f"{self.host}/api/chat"

        logger.info(f"初始化Ollama后端: host={self.host}, model={self.model}")

        # 检查连接
        if not self._check_connection():
            logger.warning(f"无法连接到Ollama服务器: {self.host}")

    def _check_connection(self) -> bool:
        """
        检查Ollama服务器连接

        Returns:
            bool: 连接是否成功
        """
        try:
            # Ollama有一个/api/tags端点可以列出所有模型
            response = requests.get(
                f"{self.host}/api/tags",
                timeout=10
            )
            return response.status_code == 200
        except Exception as e:
            logger.debug(f"连接检查失败: {e}")
            return False

    def is_available(self) -> bool:
        """
        检查后端是否可用

        Returns:
            bool: 后端是否可用
        """
        return self._check_connection()

    def chat_completion(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.3,
        max_tokens: int = 2000,
        timeout: int = None,
        **kwargs
    ) -> Optional[str]:
        """
        调用Ollama进行对话补全

        Args:
            messages: 消息列表，格式 [{"role": "user", "content": "..."}]
            temperature: 温度参数（0-1）
            max_tokens: 最大生成token数
            timeout: 超时时间（秒），None则使用默认值
            **kwargs: 其他参数

        Returns:
            str: 模型响应内容，失败返回None
        """
        if timeout is None:
            timeout = self.timeout

        try:
            # 构建Ollama请求格式
            payload = {
                "model": self.model,
                "messages": messages,
                "stream": False,  # 不使用流式响应
                "options": {
                    "temperature": temperature,
                    "num_predict": max_tokens,  # Ollama使用num_predict而不是max_tokens
                }
            }

            # 添加其他可能的选项
            if "top_p" in kwargs:
                payload["options"]["top_p"] = kwargs["top_p"]
            if "top_k" in kwargs:
                payload["options"]["top_k"] = kwargs["top_k"]

            logger.debug(f"发送Ollama请求: model={self.model}, messages_count={len(messages)}")

            # 发送请求
            response = requests.post(
                self.chat_endpoint,
                json=payload,
                timeout=timeout
            )

            # 检查响应状态
            if response.status_code != 200:
                logger.error(f"Ollama请求失败: status={response.status_code}, body={response.text}")
                return None

            # 解析响应
            result = response.json()

            # Ollama的响应格式: {"message": {"role": "assistant", "content": "..."}, "done": true}
            if "message" in result and "content" in result["message"]:
                content = result["message"]["content"]
                logger.debug(f"Ollama响应成功: length={len(content)}")
                return content
            else:
                logger.error(f"Ollama响应格式异常: {result}")
                return None

        except requests.exceptions.Timeout:
            logger.error(f"Ollama请求超时（{timeout}秒）")
            return None
        except requests.exceptions.ConnectionError:
            logger.error(f"无法连接到Ollama服务器: {self.host}")
            return None
        except Exception as e:
            logger.error(f"Ollama请求异常: {e}", exc_info=True)
            return None

    def get_backend_name(self) -> str:
        """
        获取后端名称

        Returns:
            str: 后端名称
        """
        return f"ollama({self.model}@{self.host})"

    def list_models(self) -> Optional[List[str]]:
        """
        列出所有可用的模型

        Returns:
            List[str]: 模型名称列表，失败返回None
        """
        try:
            response = requests.get(
                f"{self.host}/api/tags",
                timeout=10
            )

            if response.status_code == 200:
                result = response.json()
                if "models" in result:
                    return [model["name"] for model in result["models"]]

            return None
        except Exception as e:
            logger.error(f"获取模型列表失败: {e}")
            return None
