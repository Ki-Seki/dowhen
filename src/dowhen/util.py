# Licensed under the Apache License: http://www.apache.org/licenses/LICENSE-2.0
# For details: https://github.com/gaogaotiantian/dowhen/blob/master/NOTICE


from __future__ import annotations

import functools
import inspect
import re
import warnings
from collections.abc import Callable
from types import CodeType, FrameType, FunctionType, MethodType, ModuleType
from typing import Any

from .types import IdentifierType


def getrealsourcelines(obj) -> tuple[list[str], int]:
    try:
        lines, start_line = inspect.getsourcelines(obj)
        # We need to find the actual definition of the function/class
        # when it is decorated
        while lines[0].strip().startswith("@"):
            # If the first line is a decorator, we need to skip it
            # and move to the next line
            lines.pop(0)
            start_line += 1
    except OSError:
        lines, start_line = [], obj.co_firstlineno

    return lines, start_line


@functools.lru_cache(maxsize=256)
def get_all_code_objects(code: CodeType) -> list[CodeType]:
    """
    Recursively get all code objects from the given code object.
    """
    all_code_objects = []
    stack = [code]
    while stack:
        current_code = stack.pop()
        assert isinstance(current_code, CodeType)

        all_code_objects.append(current_code)
        for const in current_code.co_consts:
            if isinstance(const, CodeType):
                stack.append(const)

    return all_code_objects


@functools.lru_cache(maxsize=256)
def get_line_numbers(
    code: CodeType, identifier: IdentifierType | tuple[IdentifierType, ...]
) -> dict[CodeType, list[int]]:
    if not isinstance(identifier, tuple):
        identifier = (identifier,)

    line_numbers_ret: dict[CodeType, list[int]] = {}
    line_numbers_sets = []

    lines, start_line = getrealsourcelines(code)

    for ident in identifier:
        if isinstance(ident, int):
            line_numbers_set = {ident}
        else:
            if isinstance(ident, str) or isinstance(ident, re.Pattern):
                line_numbers_set = set()
                for i, line in enumerate(lines):
                    line = line.strip()
                    if (isinstance(ident, str) and line.startswith(ident)) or (
                        isinstance(ident, re.Pattern) and ident.match(line)
                    ):
                        line_number = start_line + i
                        line_numbers_set.add(line_number)
            else:
                raise TypeError(f"Unknown identifier type: {type(ident)}")

        if not line_numbers_set:
            return {}
        line_numbers_sets.append(line_numbers_set)

    agreed_line_numbers = set.intersection(*line_numbers_sets)

    all_co_lines = set()
    for sub_code in get_all_code_objects(code):
        co_lines = set(line[2] for line in sub_code.co_lines() if line[2] is not None)
        all_co_lines.update(co_lines)
        for line_number in agreed_line_numbers:
            if line_number in co_lines:
                line_numbers_ret.setdefault(sub_code, []).append(line_number)

    # Find fallback lines for non-executable code lines
    fallback_line_numbers: set[int] = set()
    for inexec_line in sorted(agreed_line_numbers - all_co_lines):
        next_exec_line = min(
            (line for line in all_co_lines if line > inexec_line), default=None
        )
        if next_exec_line is not None:
            fallback_line_numbers.add(next_exec_line)

    # Add fallback lines to the line_numbers_ret
    for sub_code in get_all_code_objects(code):
        for fallback_line in fallback_line_numbers:
            if fallback_line in (line[2] for line in sub_code.co_lines()):
                warnings.warn(
                    f"One or more lines in code object {code} are not executable, "
                    f"falling back to next executable line {fallback_line}.",
                    stacklevel=3,
                )
                line_numbers_ret.setdefault(sub_code, []).append(fallback_line)

    for line_numbers in line_numbers_ret.values():
        line_numbers.sort()

    return line_numbers_ret


@functools.lru_cache(maxsize=256)
def get_func_args(func: Callable) -> list[str]:
    args = inspect.getfullargspec(inspect.unwrap(func)).args
    # For bound methods, skip the first argument since it's already bound
    if inspect.ismethod(func):
        return args[1:]
    else:
        return args


def call_in_frame(func: Callable, frame: FrameType, **kwargs) -> Any:
    f_locals = frame.f_locals
    args = []
    for arg in get_func_args(func):
        if arg == "_frame":
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
    import hashlib

    source = inspect.getsource(entity)
    return hashlib.md5(source.encode("utf-8")).hexdigest()[-8:]


def clear_all() -> None:
    from .instrumenter import Instrumenter

    Instrumenter().clear_all()
    get_all_code_objects.cache_clear()
    get_line_numbers.cache_clear()
    get_func_args.cache_clear()
