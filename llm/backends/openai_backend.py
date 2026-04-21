"""
OpenAI API 后端实现
支持 OpenAI 官方 API 和兼容的本地服务（如 vLLM）
"""
from typing import Optional, List, Dict
from loguru import logger
from .base import BaseLLMBackend


class OpenAIBackend(BaseLLMBackend):
    """OpenAI API 后端（兼容 OpenAI API 的服务）"""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: str = "gpt-4o-mini",
        **kwargs
    ):
        """
        初始化 OpenAI 后端

        Args:
            api_key: API密钥，默认为空字符串
            base_url: API服务地址，默认使用本地服务器
            model: 模型名称
            **kwargs: 其他配置
        """
        super().__init__(api_key=api_key, base_url=base_url, model=model, **kwargs)

        self.api_key = api_key if api_key is not None else ""
        self.base_url = base_url if base_url is not None else "http://10.12.208.86:8502"
        self.model = model
        self.client = None

        self._initialize_client()

    def _initialize_client(self):
        """初始化 OpenAI 客户端"""
        try:
            from openai import OpenAI
            self.client = OpenAI(api_key=self.api_key, base_url=self.base_url)
            logger.info(
                f"OpenAI 后端初始化成功 | 模型: {self.model} | 服务: {self.base_url}"
            )
        except ImportError:
            logger.error("未安装 openai 包，请运行: pip install openai")
            self.client = None
        except Exception as e:
            logger.error(f"OpenAI 后端初始化失败: {e}")
            self.client = None

    def is_available(self) -> bool:
        """检查后端是否可用"""
        return self.client is not None

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
            messages: 消息列表
            temperature: 温度参数
            max_tokens: 最大token数
            timeout: 超时时间
            **kwargs: 其他参数

        Returns:
            生成的文本
        """
        if not self.is_available():
            logger.error("OpenAI 后端不可用")
            return None

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                timeout=timeout,
                **kwargs
            )

            # 提取结果
            choice = response.choices[0]
            result = choice.message.content
            finish_reason = choice.finish_reason

            # 详细诊断空内容的原因
            if result is None:
                logger.warning(f"⚠️  OpenAI 后端返回空内容")
                logger.warning(f"   finish_reason: {finish_reason}")
                logger.warning(f"   model: {self.model}")
                logger.warning(f"   prompt_tokens: {getattr(response.usage, 'prompt_tokens', 'N/A')}")
                logger.warning(f"   completion_tokens: {getattr(response.usage, 'completion_tokens', 'N/A')}")
                logger.warning(f"   max_tokens设置: {max_tokens}")

                # 分析可能的原因
                if finish_reason == "length":
                    logger.warning(f"   ❌ 原因: 输出超过max_tokens限制 ({max_tokens})，建议增大max_tokens")
                elif finish_reason == "content_filter":
                    logger.warning(f"   ❌ 原因: 触发内容安全过滤")
                    logger.warning(f"   提示内容（前200字符）: {messages[-1]['content'][:200] if messages else 'N/A'}")
                else:
                    logger.warning(f"   ❌ 原因未知，finish_reason={finish_reason}")

                return None

            logger.debug(f"OpenAI 后端推理成功，生成 {len(result)} 字符 (finish_reason={finish_reason})")
            return result

        except Exception as e:
            logger.error(f"❌ OpenAI 后端推理失败: {e}")
            logger.error(f"   模型: {self.model}")
            logger.error(f"   base_url: {self.base_url}")
            logger.error(f"   消息数量: {len(messages) if messages else 0}")
            if messages:
                logger.error(f"   最后一条消息长度: {len(messages[-1].get('content', ''))} 字符")
            return None

    def get_backend_name(self) -> str:
        """获取后端名称"""
        return f"OpenAI ({self.model})"
