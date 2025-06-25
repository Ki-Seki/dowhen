# Licensed under the Apache License: http://www.apache.org/licenses/LICENSE-2.0
# For details: https://github.com/gaogaotiantian/dowhen/blob/master/NOTICE.txt

"""
工具函数模块 - 提供各种辅助功能
包含：
1. 行号解析和匹配
2. 函数参数处理
3. 在特定帧中调用函数
4. 源代码哈希计算
"""

from __future__ import annotations

import functools
import inspect
from collections.abc import Callable
from types import CodeType, FrameType, FunctionType, MethodType, ModuleType
from typing import Any


def get_line_numbers(
    code: CodeType, identifier: int | str | list | tuple
) -> list[int] | None:
    """
    根据标识符获取代码对象中匹配的行号列表
    
    Args:
        code: 代码对象
        identifier: 标识符，可以是：
            - int: 绝对行号
            - str: 代码片段（查找以此开头的行）或相对行号（如"+5"）
            - list/tuple: 多个标识符的组合
            
    Returns:
        匹配的行号列表，如果没有匹配则返回None
    """
    if not isinstance(identifier, (list, tuple)):
        identifier = [identifier]

    line_numbers_sets = []

    for ident in identifier:
        if isinstance(ident, int):
            # 绝对行号
            line_numbers_sets.append({ident})
        elif isinstance(ident, str):
            if ident.startswith("+") and ident[1:].isdigit():
                # 相对行号，如"+5"表示从函数开始后第5行
                line_numbers_sets.append({code.co_firstlineno + int(ident[1:])})
            else:
                # 代码片段匹配
                lines, start_line = inspect.getsourcelines(code)
                line_numbers = set()
                for i, line in enumerate(lines):
                    if line.strip().startswith(ident):
                        line_number = start_line + i
                        line_numbers.add(line_number)
                line_numbers_sets.append(line_numbers)
        else:
            raise TypeError(f"Unknown identifier type: {type(ident)}")

    # 取所有标识符的交集
    agreed_line_numbers = set.intersection(*line_numbers_sets)
    # 过滤出代码对象中实际存在的行号
    agreed_line_numbers = {
        line_number
        for line_number in agreed_line_numbers
        if line_number in (line[2] for line in code.co_lines())
    }
    if not agreed_line_numbers:
        return None

    return sorted(agreed_line_numbers)


@functools.lru_cache(maxsize=256)
def get_func_args(func: Callable) -> list[str]:
    """
    获取函数的参数名列表（带缓存）
    
    Args:
        func: 函数对象
        
    Returns:
        参数名列表
    """
    return inspect.getfullargspec(func).args


def call_in_frame(func: Callable, frame: FrameType, **kwargs) -> Any:
    """
    在指定的帧上下文中调用函数
    
    这个函数会从帧的局部变量中提取函数所需的参数，
    特殊参数"_frame"会被替换为帧对象本身
    
    Args:
        func: 要调用的函数
        frame: 执行帧
        
    Returns:
        函数执行结果
    """
    f_locals = frame.f_locals
    args = []
    for arg in get_func_args(func):
        if arg == "_frame":
            # 特殊参数，传入帧对象
            argval = frame
        elif arg == "_retval":
            if "retval" not in kwargs:
                raise TypeError("You can only use '_retval' in <return> callbacks.")
            argval = kwargs["retval"]
        elif arg in f_locals:
            argval = f_locals[arg]
        else:
            raise TypeError(f"Argument '{arg}' not found in frame locals.")
        args.append(argval)
    return func(*args)


def get_source_hash(entity: CodeType | FunctionType | MethodType | ModuleType | type):
    """
    计算实体源代码的哈希值
    
    用于检测源代码是否发生变化，确保插桩的有效性
    
    Args:
        entity: 要计算哈希的实体
        
    Returns:
        源代码的MD5哈希值的后8位
    """
    import hashlib

    source = inspect.getsource(entity)
    return hashlib.md5(source.encode("utf-8")).hexdigest()[-8:]
