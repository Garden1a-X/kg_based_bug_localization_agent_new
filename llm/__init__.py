"""
LLM 客户端模块
"""
from llm.llm_client import LLMClient
from llm.openai_client import OpenAIClient  # 保留向后兼容

__all__ = ['LLMClient', 'OpenAIClient']
