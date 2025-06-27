# Licensed under the Apache License: http://www.apache.org/licenses/LICENSE-2.0
# For details: https://github.com/gaogaotiantian/dowhen/blob/master/NOTICE

"""
测试工具模块
提供测试过程中需要的辅助功能，包括覆盖率控制和PDB测试支持
"""

import contextlib
import io
import sys
import textwrap


@contextlib.contextmanager
def disable_coverage():
    """
    临时禁用代码覆盖率监控的上下文管理器
    
    在某些测试场景中，我们需要暂时禁用覆盖率监控，
    以避免与代码插桩功能产生冲突
    """
    try:
        import coverage

        cov = coverage.Coverage().current()
    except ModuleNotFoundError:
        cov = None

    if cov is None:
        yield
        return

    # 暂停覆盖率监控
    cov.stop()
    yield
    # 重新启动覆盖率监控
    cov.start()


@contextlib.contextmanager
def do_pdb_test(command):
    """
    用于测试PDB调试器交互的上下文管理器
    
    Args:
        command: 要在PDB中执行的命令字符串
        
    Yields:
        输出流对象，可以用来检查PDB的输出
    """
    # 准备命令输入流
    command_input = io.StringIO(textwrap.dedent(command))
    output = io.StringIO()

    # 保存原始的stdin和stdout
    _stdin = sys.stdin
    _stdout = sys.stdout
    try:
        # 重定向输入输出流
        sys.stdin = command_input
        sys.stdout = output
        # 在禁用覆盖率的情况下执行测试
        with disable_coverage():
            yield output
    finally:
        # 恢复原始的输入输出流
        sys.stdin = _stdin
        sys.stdout = _stdout
