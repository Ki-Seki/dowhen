# Licensed under the Apache License: http://www.apache.org/licenses/LICENSE-2.0
# For details: https://github.com/gaogaotiantian/dowhen/blob/master/NOTICE.txt

"""
事件处理器模块 - 管理触发器和回调的生命周期
这个模块负责：
1. 将触发器和回调绑定在一起
2. 管理处理器的启用/禁用状态
3. 支持回调链式调用
4. 提供上下文管理器接口
"""

from __future__ import annotations

import sys
from types import FrameType
from typing import Any, Callable

from .callback import Callback
from .instrumenter import Instrumenter
from .trigger import Trigger

# 禁用标志
DISABLE = sys.monitoring.DISABLE


class EventHandler:
    """
    事件处理器类 - 绑定触发器和回调函数
    
    管理单个监控点的完整生命周期，包括：
    - 触发条件检查
    - 回调函数执行
    - 启用/禁用控制
    - 资源清理
    """
    
    def __init__(self, trigger: Trigger, callback: Callback):
        """
        初始化事件处理器
        
        Args:
            trigger: 触发器对象，定义何时触发
            callback: 回调对象，定义触发时执行什么
        """
        self.trigger = trigger
        self.callbacks: list[Callback] = [callback]  # 支持多个回调链式执行
        self.disabled = False  # 是否禁用
        self.removed = False   # 是否已移除

    def disable(self) -> None:
        """禁用处理器"""
        if self.removed:
            raise RuntimeError("Cannot disable a removed handler.")
        self.disabled = True

    def enable(self) -> None:
        """启用处理器"""
        if self.removed:
            raise RuntimeError("Cannot enable a removed handler.")
        if self.disabled:
            self.disabled = False
            # 重启事件监控
            Instrumenter().restart_events()

    def submit(self) -> None:
        """将处理器提交给插桩器"""
        Instrumenter().submit(self)

    def remove(self) -> None:
        """移除处理器并清理资源"""
        Instrumenter().remove_handler(self)
        self.removed = True

    def __call__(self, frame: FrameType, **kwargs) -> Any:
        """
        处理器被调用时的执行逻辑
        
        检查触发条件，如果满足则依次执行所有回调
        """
        if not self.disabled:
            should_fire = self.trigger.should_fire(frame)
            if should_fire is DISABLE:
                # 触发条件返回DISABLE，禁用处理器
                self.disable()
            elif should_fire:
                # 依次执行所有回调
                for cb in self.callbacks:
                    if cb(frame, **kwargs) is DISABLE:
                        self.disable()

        if self.disabled:
            return DISABLE

    def __enter__(self) -> "EventHandler":
        """上下文管理器入口"""
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        """上下文管理器出口，自动清理资源"""
        self.remove()

    def bp(self) -> "EventHandler":
        """向当前处理器添加断点回调"""
        from .callback import Callback

        self.callbacks.append(Callback.bp())
        return self

    def do(self, func: str | Callable) -> "EventHandler":
        """向当前处理器添加执行代码回调"""
        from .callback import Callback

        self.callbacks.append(Callback.do(func))
        return self

    def goto(self, target: str | int) -> "EventHandler":
        """向当前处理器添加跳转回调"""
        from .callback import Callback

        self.callbacks.append(Callback.goto(target))
        return self
