# Licensed under the Apache License: http://www.apache.org/licenses/LICENSE-2.0
# For details: https://github.com/gaogaotiantian/dowhen/blob/master/NOTICE.txt

"""
回调模块 - 定义各种类型的回调函数
这个模块包含了dowhen工具的核心回调功能，包括：
1. do - 执行任意代码
2. bp - 设置断点进入调试器
3. goto - 跳转到指定行号
"""

from __future__ import annotations

import ctypes
import inspect
import sys
import warnings
from collections.abc import Callable
from types import CodeType, FrameType, FunctionType, MethodType, ModuleType
from typing import TYPE_CHECKING, Any

from .util import call_in_frame, get_line_numbers

if TYPE_CHECKING:  # pragma: no cover
    from .handler import EventHandler

# 禁用标志，用于停止监控
DISABLE = sys.monitoring.DISABLE


class Callback:
    """
    回调类 - 用于定义在触发点执行的操作
    
    支持三种类型的回调：
    1. 字符串形式的Python代码
    2. Python函数或方法
    3. 特殊的内置操作（如goto）
    """
    
    def __init__(self, func: str | Callable, **kwargs):
        """初始化回调对象"""
        if isinstance(func, str):
            # 字符串形式的代码或特殊指令
            pass
        elif inspect.isfunction(func):
            # 普通函数，获取参数列表用于后续调用
            self.func_args = inspect.getfullargspec(func).args
        elif inspect.ismethod(func):
            # 方法，获取参数列表用于后续调用
            self.func_args = inspect.getfullargspec(func).args
        else:
            raise TypeError(f"Unsupported callback type: {type(func)}. ")
        self.func = func
        self.kwargs = kwargs
        
    def __call__(self, frame, **kwargs) -> Any:
        """执行回调函数"""
        ret = None
        if isinstance(self.func, str):
            if self.func == "goto":  # pragma: no cover
                # 特殊的goto操作，改变执行流程
                self._call_goto(frame)
            else:
                # 执行字符串形式的Python代码
                self._call_code(frame)
        elif inspect.isfunction(self.func) or inspect.ismethod(self.func):
            # 调用Python函数或方法
            ret = self._call_function(frame, **kwargs)
        else:  # pragma: no cover
            assert False, "Unknown callback type"

        # 在Python < 3.13版本中需要手动同步局部变量
        if sys.version_info < (3, 13):
            LocalsToFast = ctypes.pythonapi.PyFrame_LocalsToFast
            LocalsToFast.argtypes = [ctypes.py_object, ctypes.c_int]
            LocalsToFast(frame, 0)

        # 如果返回DISABLE，则停止监控
        if ret is DISABLE:
            return DISABLE

    def _call_code(self, frame: FrameType) -> None:
        """执行字符串形式的Python代码"""
        assert isinstance(self.func, str)
        # 在当前帧的上下文中执行代码
        exec(self.func, frame.f_globals, frame.f_locals)

    def _call_function(self, frame: FrameType, **kwargs) -> Any:
        """调用Python函数或方法"""
        assert isinstance(self.func, (FunctionType, MethodType))
        # 在当前帧的上下文中调用函数
        writeback = call_in_frame(self.func, frame, **kwargs)

        f_locals = frame.f_locals
        if isinstance(writeback, dict):
            # 如果函数返回字典，将其写回到局部变量
            for arg, val in writeback.items():
                if arg not in f_locals:
                    raise TypeError(f"Argument '{arg}' not found in frame locals.")
                f_locals[arg] = val
        elif writeback is DISABLE:
            # 如果返回DISABLE，停止监控
            return DISABLE
        elif writeback is not None:
            raise TypeError(
                "Callback function must return a dictionary for writeback, or None, "
                f"got {type(writeback)} instead."
            )

    def _call_goto(self, frame: FrameType) -> None:  # pragma: no cover
        """执行goto操作，跳转到指定行号"""
        # 改变frame.f_lineno只能在trace函数中进行，所以这个函数无法被覆盖率测试覆盖
        target = self.kwargs["target"]
        line_numbers = get_line_numbers(frame.f_code, target)
        if line_numbers is None:
            raise ValueError(f"Could not determine line number for target: {target}")
        elif len(line_numbers) > 1:
            raise ValueError(
                f"Multiple line numbers found for target '{target}': {line_numbers}"
            )
        line_number = line_numbers[0]
        with warnings.catch_warnings():
            # 在Python 3.12中这会产生RuntimeWarning
            warnings.simplefilter("ignore", RuntimeWarning)
            # mypy认为f_lineno是只读的
            frame.f_lineno = line_number  # type: ignore

    @classmethod
    def do(cls, func: str | Callable) -> Callback:
        """创建一个执行代码的回调"""
        return cls(func)

    @classmethod
    def goto(cls, target: str | int) -> Callback:
        """创建一个跳转到指定目标的回调"""
        return cls("goto", target=target)

    @classmethod
    def bp(cls) -> Callback:
        """创建一个断点回调，会启动pdb调试器"""
        def do_breakpoint(_frame: FrameType) -> None:  # pragma: no cover
            import pdb

            p = pdb.Pdb()
            p.set_trace(_frame)
            if hasattr(p, "set_enterframe"):
                # set_enterframe is backported to 3.12 so the early versions
                # of Python 3.12 will not have this method
                with p.set_enterframe(_frame):
                    p.user_line(_frame)
            else:
                p.user_line(_frame)

        return cls(do_breakpoint)

    def when(
        self,
        entity: CodeType | FunctionType | MethodType | ModuleType | type,
        *identifiers: str | int | tuple | list,
        condition: str | Callable[..., bool | Any] | None = None,
        source_hash: str | None = None,
    ) -> "EventHandler":
        """
        为当前回调设置触发条件
        
        Args:
            entity: 要监控的实体（函数、方法、模块、类或代码对象）
            identifiers: 标识符，用于指定具体的监控点
            condition: 触发条件，可以是字符串表达式或函数
            source_hash: 源代码哈希值，用于验证代码是否发生变化
            
        Returns:
            EventHandler: 事件处理器对象
        """
        from .trigger import when

        trigger = when(
            entity, *identifiers, condition=condition, source_hash=source_hash
        )

        from .handler import EventHandler

        handler = EventHandler(trigger, self)
        handler.submit()

        return handler


# 导出三个主要的回调函数
bp = Callback.bp      # 断点回调
do = Callback.do      # 执行代码回调
goto = Callback.goto  # 跳转回调
