import sys
import types

# ========================
# 注册工具 ID（确保不冲突）
# ========================
TOOL_ID = 3
TOOL_NAME = "full_demo_tool"

sys.monitoring.use_tool_id(TOOL_ID, TOOL_NAME)

print(f"✅ 注册工具 ID = {TOOL_ID}, 名称 = {TOOL_NAME}")

# ========================
# 定义通用回调函数
# ========================
def event_callback(*args):
    print(f"📍 callback args = {args}")
    print(f'{type(args[0])} {args[0].co_name} {args[1]}')
    return 0

def disable_after_first(code, offset, *args):
    print(f"🚫 DISABLE after first call in {code.co_name} at offset {offset}")
    return sys.monitoring.DISABLE

# ========================
# 注册所有可用事件的回调
# ========================
ALL_EVENTS = vars(sys.monitoring.events)
for event_name, event_val in ALL_EVENTS.items():
    if isinstance(event_val, int):
        try:
            sys.monitoring.register_callback(TOOL_ID, event_val, event_callback)
        except Exception as e:
            print(f"⚠️ 注册失败: {event_name}: {e}")

# 注册 DISABLE 示例回调（比如 CALL 事件）
sys.monitoring.register_callback(TOOL_ID, sys.monitoring.events.CALL, disable_after_first)

# ========================
# 示例代码（函数/类/生成器/异常）
# ========================
def add(x, y):
    return x + y

def raise_error():
    raise ValueError("boom!")

def gen():
    yield "hello"
    yield "world"

async def coro():
    return "async"

class MyClass:
    def method(self, z):
        return z * 2

    @classmethod
    def cls_method(cls):
        return "cls"

    @staticmethod
    def static():
        return "static"

# ========================
# 激活事件监听（设置 Code 对象局部事件）
# ========================
def apply_local_events(fn):
    if hasattr(fn, "__code__"):
        code = fn.__code__
    elif isinstance(fn, types.FunctionType):
        code = fn
    else:
        return
    sys.monitoring.set_local_events(TOOL_ID, code, sys.monitoring.events.LINE)

all_targets = [
    add,
    raise_error,
    gen,
    coro,
    MyClass().method,
    MyClass.cls_method,
    MyClass.static,
]

for fn in all_targets:
    apply_local_events(fn)

# ========================
# 执行被监控函数们
# ========================
print("\n🎬 执行被监控代码:")

print(add(1, 2))

try:
    raise_error()
except Exception as e:
    print(f"Caught: {e}")

g = gen()
print(next(g))
print(next(g))

import asyncio
asyncio.run(coro())

obj = MyClass()
print(obj.method(10))
print(MyClass.cls_method())
print(MyClass.static())

# ========================
# 测试 DISABLE 恢复功能
# ========================
print("\n🔄 使用 restart_events 恢复已禁用事件")
sys.monitoring.restart_events()
print(add(2, 3))  # 如果 DISABLE 生效，会打印出“再启用”后的事件

# ========================
# 工具释放
# ========================
print("\n🧹 释放工具 ID")
sys.monitoring.free_tool_id(TOOL_ID)
