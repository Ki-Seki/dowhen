from dowhen import do

def f(x):
    x += 100
    # Let's change the value of x before return
    return x

# do("x = 1") is the callback
# when(f, "return x") is the trigger
# This is equivalent to:
# handler = when(f, "return x").do("x = 1")
handler = do("x = 1").when(f, "return x")
# x = 1 is executed before "return x"
assert f(0) == 1

# You can remove the handler
handler.remove()
assert f(0) == 100
