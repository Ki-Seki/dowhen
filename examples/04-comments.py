from dowhen import when
import inspect


def func():
    """This is a doc str
    another line
    """

    x = 2  ; '''
    another complex example comment
    x = 2
    '''

    x = 2
    x = 2

    x = 3  # comment
    
    x = 4
    return x


code = func.__code__

with when(func, 'x = 2').do('print("hello")'):
    print(func())

with when(func, 'return x').do('x=1'):
    print(func())  # Should print 1


with when(func, '# comment').do('x=1'):
    print(func())  # this will raise error

