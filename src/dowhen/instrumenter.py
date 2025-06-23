# Licensed under the Apache License: http://www.apache.org/licenses/LICENSE-2.0
# For details: https://github.com/gaogaotiantian/dowhen/blob/master/NOTICE.txt

"""
插桩器模块 - 核心的代码监控和事件分发系统
这个模块负责：
1. 使用Python的sys.monitoring API进行代码监控
2. 管理所有的事件处理器
3. 分发监控事件到相应的处理器
4. 提供单例模式确保全局唯一的监控实例
"""

from __future__ import annotations

import sys
from collections import defaultdict
from types import CodeType, FrameType
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from .handler import EventHandler

# 监控事件类型常量
E = sys.monitoring.events
DISABLE = sys.monitoring.DISABLE


class Instrumenter:
    """
    插桩器类 - 使用sys.monitoring API实现代码监控
    
    这是一个单例类，负责：
    1. 注册监控回调函数
    2. 管理代码对象的事件监控
    3. 分发事件到相应的处理器
    """
    
    _intialized: bool = False

    def __new__(cls, *args, **kwargs) -> Instrumenter:
        """单例模式实现"""
        if not hasattr(cls, "_instance"):
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, tool_id: int = 4):
        """
        Initialize the instrumenter with a monitoring tool ID.
        
        Args:
            tool_id: Tool ID for sys.monitoring registration. Defaults to 4 to avoid
                    conflicts with predefined IDs (0=debugger, 1=coverage, 2=profiler, 5=optimizer).
                    See: https://docs.python.org/3.12/library/sys.monitoring.html
        """
        if not self._intialized:
            self.tool_id = tool_id
            # 按代码对象组织的处理器映射
            # 结构：{CodeType: {"line": {line_number: [handlers]}, "start": [handlers], "return": [handlers]}}
            self.handlers: defaultdict[CodeType, dict] = defaultdict(dict)

            # 向sys.monitoring注册监控工具
            sys.monitoring.use_tool_id(self.tool_id, "dowhen instrumenter")
            
            # 注册各种事件的回调函数
            sys.monitoring.register_callback(self.tool_id, E.LINE, self.line_callback)
            sys.monitoring.register_callback(
                self.tool_id, E.PY_RETURN, self.return_callback
            )
            sys.monitoring.register_callback(
                self.tool_id, E.PY_START, self.start_callback
            )
            self._intialized = True

    def clear_all(self) -> None:
        """清除所有监控和处理器"""
        for code in self.handlers:
            # 停止对每个代码对象的监控
            sys.monitoring.set_local_events(self.tool_id, code, E.NO_EVENTS)
        self.handlers.clear()

    def submit(self, event_handler: "EventHandler") -> None:
        """
        提交事件处理器到插桩器
        
        根据处理器的触发器配置相应的监控事件
        """
        trigger = event_handler.trigger
        for event in trigger.events:
            code = event.code
            if event.event_type == "line":
                # 行号事件
                assert (
                    isinstance(event.event_data, dict)
                    and "line_number" in event.event_data
                )
                self.register_line_event(
                    code,
                    event.event_data["line_number"],
                    event_handler,
                )
            elif event.event_type == "start":
                # 函数开始事件
                self.register_start_event(code, event_handler)
            elif event.event_type == "return":
                # 函数返回事件
                self.register_return_event(code, event_handler)

    def register_line_event(
        self, code: CodeType, line_number: int, event_handler: "EventHandler"
    ) -> None:
        """注册行号事件监控"""
        # 将处理器添加到指定代码对象的指定行号
        self.handlers[code].setdefault("line", {}).setdefault(line_number, []).append(
            event_handler
        )

        # 启用该代码对象的行号监控
        events = sys.monitoring.get_local_events(self.tool_id, code)
        sys.monitoring.set_local_events(self.tool_id, code, events | E.LINE)
        sys.monitoring.restart_events()

    def line_callback(self, code: CodeType, line_number: int):  # pragma: no cover
        """行号事件回调函数"""
        if code in self.handlers:
            # 获取指定行号的处理器 + 通用行号处理器（None表示所有行）
            handlers = self.handlers[code].get("line", {}).get(line_number, [])
            handlers.extend(self.handlers[code].get("line", {}).get(None, []))
            if handlers:
                return self._process_handlers(handlers, sys._getframe(1))
        return sys.monitoring.DISABLE

    def register_start_event(
        self, code: CodeType, event_handler: "EventHandler"
    ) -> None:
        """注册函数开始事件监控"""
        self.handlers[code].setdefault("start", []).append(event_handler)

        # 启用该代码对象的函数开始监控
        events = sys.monitoring.get_local_events(self.tool_id, code)
        sys.monitoring.set_local_events(self.tool_id, code, events | E.PY_START)
        sys.monitoring.restart_events()

    def start_callback(self, code: CodeType, offset):  # pragma: no cover
        """函数开始事件回调函数"""
        if code in self.handlers:
            handlers = self.handlers[code].get("start", [])
            if handlers:
                return self._process_handlers(handlers, sys._getframe(1))
        return sys.monitoring.DISABLE

    def register_return_event(
        self, code: CodeType, event_handler: "EventHandler"
    ) -> None:
        """注册函数返回事件监控"""
        self.handlers[code].setdefault("return", []).append(event_handler)

        # 启用该代码对象的函数返回监控
        events = sys.monitoring.get_local_events(self.tool_id, code)
        sys.monitoring.set_local_events(self.tool_id, code, events | E.PY_RETURN)
        sys.monitoring.restart_events()

    def return_callback(self, code: CodeType, offset, retval):  # pragma: no cover
        """函数返回事件回调函数"""
        if code in self.handlers:
            handlers = self.handlers[code].get("return", [])
            if handlers:
                return self._process_handlers(handlers, sys._getframe(1))
        return sys.monitoring.DISABLE

    def _process_handlers(
        self, handlers: list["EventHandler"], frame: FrameType
    ):  # pragma: no cover
        """处理事件处理器列表"""
        disable = sys.monitoring.DISABLE
        for handler in handlers:
            # 调用每个处理器，如果任何一个返回DISABLE则禁用监控
            disable = handler(frame) and disable
        return sys.monitoring.DISABLE if disable else None

    def restart_events(self) -> None:
        """重启事件监控"""
        sys.monitoring.restart_events()

    def remove_handler(self, event_handler: "EventHandler") -> None:
        """
        移除事件处理器
        
        从所有相关的监控点移除指定的处理器，并在必要时停止监控
        """
        trigger = event_handler.trigger
        for event in trigger.events:
            code = event.code
            if code not in self.handlers or event.event_type not in self.handlers[code]:
                continue
                
            # 根据事件类型获取处理器列表
            if event.event_type == "line":
                assert (
                    isinstance(event.event_data, dict)
                    and "line_number" in event.event_data
                )
                handlers = self.handlers[code]["line"].get(
                    event.event_data["line_number"], []
                )
            else:
                handlers = self.handlers[code][event.event_type]

            # 从处理器列表中移除
            if event_handler in handlers:
                handlers.remove(event_handler)

                # 如果是行号事件且该行号没有其他处理器，清理该行号映射
                if event.event_type == "line" and not handlers:
                    assert (
                        isinstance(event.event_data, dict)
                        and "line_number" in event.event_data
                    )
                    del self.handlers[code]["line"][event.event_data["line_number"]]

                # 如果该事件类型没有处理器了，停止该类型的监控
                if not self.handlers[code][event.event_type]:
                    del self.handlers[code][event.event_type]
                    events = sys.monitoring.get_local_events(self.tool_id, code)
                    # 根据事件类型确定要移除的监控标志
                    removed_event = {
                        "line": E.LINE,
                        "start": E.PY_START,
                        "return": E.PY_RETURN,
                    }[event.event_type]

                    # 从监控中移除该事件类型
                    sys.monitoring.set_local_events(
                        self.tool_id, code, events & ~removed_event
                    )


def clear_all() -> None:
    """清除所有监控和处理器的全局函数"""
    Instrumenter().clear_all()
