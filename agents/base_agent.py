"""
Agent基类
所有Agent都继承此基类
"""
from abc import ABC, abstractmethod
from typing import Any, Dict
from loguru import logger


class BaseAgent(ABC):
    """Agent基类"""
    
    def __init__(self, name: str):
        """
        初始化Agent
        
        Args:
            name: Agent名称
        """
        self.name = name
        self.logger = logger.bind(agent=name)
    
    @abstractmethod
    def execute(self, *args, **kwargs) -> Any:
        """
        执行Agent的主要任务
        子类必须实现此方法
        """
        pass
    
    def log_start(self, task: str):
        """记录任务开始"""
        self.logger.info(f"[{self.name}] 开始: {task}")
    
    def log_success(self, message: str):
        """记录成功"""
        self.logger.success(f"[{self.name}] ✓ {message}")
    
    def log_warning(self, message: str):
        """记录警告"""
        self.logger.warning(f"[{self.name}] ⚠ {message}")
    
    def log_error(self, message: str):
        """记录错误"""
        self.logger.error(f"[{self.name}] ✗ {message}")
    
    def log_info(self, message: str):
        """记录信息"""
        self.logger.info(f"[{self.name}] {message}")
