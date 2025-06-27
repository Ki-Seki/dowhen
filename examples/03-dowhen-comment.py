from dowhen import do, when


def func():
    x = 2
    # comment
    return x

with when(func, 'return x').do('x=1'):
    print(func())  # Should print 1


with when(func, '# comment').do('x=1'):
    print(func())  # this will raise error

