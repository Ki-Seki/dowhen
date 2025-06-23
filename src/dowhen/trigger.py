# Licensed under the Apache License: http://www.apache.org/licenses/LICENSE-2.0
# For details: https://github.com/gaogaotiantian/dowhen/blob/master/NOTICE.txt

"""
触发器模块 - 定义何时执行回调函数
这个模块负责：
1. 解析和处理触发条件
2. 管理代码对象和事件类型
3. 提供when接口用于设置触发点
"""

from __future__ import annotations

import inspect
from collections.abc import Callable
from types import CodeType, FrameType, FunctionType, MethodType, ModuleType
from typing import TYPE_CHECKING, Any, Literal

from .util import call_in_frame, get_line_numbers, get_source_hash

if TYPE_CHECKING:  # pragma: no cover
    from .callback import Callback
    from .handler import EventHandler


class _Event:
    """
    事件类 - 表示一个具体的监控事件
    
    包含代码对象、事件类型和相关数据
    """
    def __init__(
        self,
        code: CodeType,
        event_type: Literal["line", "start", "return"],
        event_data: dict | None,
    ):
        self.code = code               # 要监控的代码对象
        self.event_type = event_type   # 事件类型：行号、函数开始、函数返回
        self.event_data = event_data or {}  # 事件相关数据（如行号）


class Trigger:
    """
    触发器类 - 管理何时触发回调
    
    负责：
    1. 管理多个事件
    2. 处理触发条件
    3. 提供回调绑定接口
    """
    def __init__(
        self,
        events: list[_Event],
        condition: str | Callable[..., bool] | None = None,
    ):
        self.events = events      # 事件列表
        self.condition = condition  # 触发条件

    @classmethod
    def _get_code_from_entity(
        cls, entity: CodeType | FunctionType | MethodType | ModuleType | type
    ) -> tuple[list[CodeType], list[CodeType]]:
        """
        从给定实体中获取代码对象
        
        返回两个列表：
        1. 直接代码对象（函数/方法的主体代码）
        2. 所有代码对象（包括嵌套的代码对象）
        """
        direct_code_objects: list[CodeType] = []
        all_code_objects: list[CodeType] = []

        entity_list = []

        # 如果是模块或类，获取其中的所有函数/方法
        if inspect.ismodule(entity) or inspect.isclass(entity):
            for _, obj in inspect.getmembers_static(
                entity, lambda o: isinstance(o, (FunctionType, MethodType, CodeType))
            ):
                entity_list.append(obj)
        else:
            entity_list.append(entity)

        # 提取直接代码对象
        for entity in entity_list:
            if inspect.isfunction(entity) or inspect.ismethod(entity):
                direct_code_objects.append(entity.__code__)
            elif inspect.iscode(entity):
                direct_code_objects.append(entity)
            else:
                raise TypeError(f"Unknown entity type: {type(entity)}")

        # 递归提取所有嵌套的代码对象（如内部函数、lambda等）
        for code in direct_code_objects:
            stack = [code]
            while stack:
                current_code = stack.pop()
                assert isinstance(current_code, CodeType)

                all_code_objects.append(current_code)
                for const in current_code.co_consts:
                    if isinstance(const, CodeType):
                        stack.append(const)

        return direct_code_objects, all_code_objects

    @classmethod
    def when(
        cls,
        entity: CodeType | FunctionType | MethodType | ModuleType | type,
        *identifiers: str | int | tuple | list,
        condition: str | Callable[..., bool | Any] | None = None,
        source_hash: str | None = None,
    ):
        """
        创建触发器的主要方法
        
        Args:
            entity: 要监控的实体
            identifiers: 标识符列表，用于指定监控点
            condition: 触发条件
            source_hash: 源代码哈希值验证
            
        Returns:
            Trigger: 触发器对象
        """
        # 验证条件表达式的语法
        if isinstance(condition, str):
            try:
                compile(condition, "<string>", "eval")
            except SyntaxError:
                raise ValueError(f"Invalid condition expression: {condition}")
        elif condition is not None and not callable(condition):
            raise TypeError(
                f"Condition must be a string or callable, got {type(condition)}"
            )

        # 验证源代码哈希值
        if source_hash is not None:
            if not isinstance(source_hash, str):
                raise TypeError(
                    f"source_hash must be a string, got {type(source_hash)}"
                )
            # 验证源代码是否发生变化
            if get_source_hash(entity) != source_hash:
                raise ValueError(
                    "The source hash does not match the entity's source code."
                )

        events = []

        # 获取代码对象
        direct_code_objects, all_code_objects = cls._get_code_from_entity(entity)

        # 如果没有指定标识符，监控所有直接代码对象的所有行
        if not identifiers:
            for code in direct_code_objects:
                events.append(_Event(code, "line", {"line_number": None}))
            return cls(events, condition=condition)

        # 处理每个标识符
        for identifier in identifiers:
            if identifier == "<start>":
                # 监控函数开始
                for code in direct_code_objects:
                    events.append(_Event(code, "start", None))
            elif identifier == "<return>":
                # 监控函数返回
                for code in direct_code_objects:
                    events.append(_Event(code, "return", None))

            # 在所有代码对象中查找匹配的行号
            for code in all_code_objects:
                line_numbers = get_line_numbers(code, identifier)
                if line_numbers is not None:
                    for line_number in line_numbers:
                        events.append(
                            _Event(code, "line", {"line_number": line_number})
                        )

        # 确保至少有一个事件被创建
        if not events:
            raise ValueError(
                "Could not set any event based on the entity and identifiers."
            )

        return cls(events, condition=condition)

    def bp(self) -> "EventHandler":
        """为当前触发器添加断点回调"""
        from .callback import Callback

        return self._submit_callback(Callback.bp())

    def do(self, func: str | Callable) -> "EventHandler":
        """为当前触发器添加执行代码回调"""
        from .callback import Callback

        return self._submit_callback(Callback.do(func))

    def goto(self, target: str | int) -> "EventHandler":
        """为当前触发器添加跳转回调"""
        from .callback import Callback

        return self._submit_callback(Callback.goto(target))

    def should_fire(self, frame: FrameType) -> bool:
        """
        判断是否应该触发回调
        
        根据设置的条件来判断是否满足触发要求
        """
        if self.condition is None:
            return True
        try:
            if isinstance(self.condition, str):
                # 字符串条件，在当前帧中求值
                return eval(self.condition, frame.f_globals, frame.f_locals)
            elif callable(self.condition):
                # 函数条件，在当前帧中调用
                return call_in_frame(self.condition, frame)
        except Exception:
            # 条件执行出错时不触发
            return False

        assert False, "Unknown condition type"  # pragma: no cover

    def _submit_callback(self, callback: "Callback") -> "EventHandler":
        """提交回调到事件处理器"""
        from .handler import EventHandler

        handler = EventHandler(self, callback)
        handler.submit()

        return handler


# 导出when函数，这是主要的用户接口
when = Trigger.when
