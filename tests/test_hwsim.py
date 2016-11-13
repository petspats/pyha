import textwrap
from functools import wraps

import pytest

from pyha.common.hwsim import HW, Meta, clock_tick, AssignToSelf, TypeNotConsistent
from pyha.common.sfix import Sfix


def test_metaclass_assigned():
    class A(HW):
        pass

    assert type(A) == Meta


def test_call_decorated():
    class A(HW):
        def main(self, *args, **kwargs):
            pass

    assert A().main.__wrapped__ == clock_tick


def test_next_init():
    class A(HW):
        def __init__(self):
            self.a = 1

    dut = A()
    assert dut.a == dut.next.a

    dut.a = 2
    assert dut.next.a != dut.a

    dut.next.a = 3
    assert dut.a == 2
    assert dut.next.a == 3


def test_float_register():
    class A(HW):
        def __init__(self):
            self.a = 1.0

        def main(self, next):
            self.next.a = next

    dut = A()
    assert dut.a == 1.0
    dut.main(2.0)
    assert dut.a == 1.0
    dut.main(3.0)
    assert dut.a == 2.0


def test_list_register():
    class A(HW):
        def __init__(self):
            self.a = [1.0, 2.0, 3.0]

        def main(self, next):
            self.next.a = [next] + self.a[:-1]

    dut = A()
    assert dut.a == [1.0, 2.0, 3.0]
    dut.main(4.0)
    assert dut.a == [1.0, 2.0, 3.0]
    dut.main(3.0)
    assert dut.a == [4.0, 1.0, 2.0]


def test_list_cascade_register():
    class A(HW):
        def __init__(self):
            self.a = [1.0, 2.0, 3.0]

        def main(self, next):
            self.next.a = [next] + self.a[:-1]
            return self.a[-1]

    class B(HW):
        def __init__(self):
            self.a = A()
            self.l = [0.0, 0.0]

        def main(self, next):
            last = self.a.main(next)
            self.next.l = [last] + self.l[:-1]

    dut = B()
    assert dut.l == [0.0, 0.0]
    dut.main(4.0)
    assert dut.l == [0.0, 0.0]
    dut.main(3.0)
    assert dut.l == [3.0, 0.0]
    dut.main(2.0)
    assert dut.l == [2.0, 3.0]
    assert dut.a.a == [3.0, 4.0, 1.0]


def test_forbid_self_assign_sfix_raises():
    class A(HW):
        def __init__(self):
            self.a = Sfix(0.0)

        def main(self, condition):
            if condition:
                self.next.a = Sfix(1.2, 3, -18)
            else:
                self.a = Sfix(2.2, 3, -18)

    expect = textwrap.dedent("""\
            Assigment to self.a, did you mean self.next.a?
            Class: A""")

    dut = A()
    dut.main(True)
    with pytest.raises(AssignToSelf) as e:
        dut.main(False)

    assert str(e.value) == expect


def test_forbid_self_assign_list_raises():
    class A(HW):
        def __init__(self):
            self.alist = [1, 2, 3]

        def main(self, condition):
            if condition:
                self.next.alist = [1, 2, 3]
            else:
                self.alist = [1, 2, 3, 4]

    expect = textwrap.dedent("""\
            Assigment to self.alist, did you mean self.next.alist?
            Class: A""")

    dut = A()
    dut.main(True)
    with pytest.raises(AssignToSelf) as e:
        dut.main(False)

    assert str(e.value) == expect


def test_forbid_self_assign_numpy():
    # numpy used to crash this check
    import numpy as np
    class A(HW):
        def __init__(self):
            self.b = np.array([1, 2, 3])

        def main(self):
            pass

    expect = {}
    dut = A()
    dut.main()


def test_self_type_consistent_raises():
    class A(HW):
        def __init__(self):
            self.a = 128

        def main(self, condition):
            if condition:
                self.next.a = 128
            else:
                self.next.a = True

    dut = A()
    dut.main(True)
    with pytest.raises(TypeNotConsistent):
        dut.main(False)


def test_self_type_consistent_initial_allowed_raises():
    class A(HW):
        def __init__(self):
            self.a = 128

        def main(self, condition):
            if condition:
                self.next.a = 128
            else:
                self.next.a = True

    expect = textwrap.dedent("""\
            Self/local not consistent type!
            Class: A
            Function: main
            Variable: a
            Old: <class 'dict'>:{'a': 128}
            New: <class 'dict'>:{'a': True}""")
    dut = A()
    dut.main(True)
    with pytest.raises(TypeNotConsistent) as e:
        dut.main(False)

    assert str(e.value) == expect


def test_self_type_consistent_sfix_raises():
    class A(HW):
        def __init__(self):
            self.a = Sfix(0.0)

        def main(self, condition):
            if condition:
                self.next.a = Sfix(1.2, 3, -18)
            else:
                self.next.a = Sfix(2.2, 3, -32)

    expect = textwrap.dedent("""\
            Self/local not consistent type!
            Class: A
            Function: main
            Variable: a
            Old: <class 'dict'>:{'a': 1.20000076294 [3:-18]}
            New: <class 'dict'>:{'a': 2.19999999995 [3:-32]}""")
    dut = A()
    dut.main(True)
    with pytest.raises(TypeNotConsistent) as e:
        dut.main(False)

    assert str(e.value) == expect


def test_self_type_consistent_sfix():
    class A(HW):
        def __init__(self):
            self.a = Sfix(0.0)

        def main(self, condition):
            if condition:
                self.next.a = Sfix(1.2, 3, -18)
            else:
                self.next.a = Sfix(2.2, 3, -18)

    dut = A()
    dut.main(True)
    dut.main(False)


def test_self_type_consistent_list():
    class A(HW):
        def __init__(self):
            self.a = [1] * 5

        def main(self):
            self.next.a = [3] * 5

    dut = A()
    dut.main()
    dut.main()


def test_self_type_consistent_list_raises():
    class A(HW):
        def __init__(self):
            self.a = [1] * 5

        def main(self):
            self.next.a = [3] * 2

    expect = textwrap.dedent("""\
            Self/local not consistent type!
            Class: A
            Function: main
            Variable: a
            Old: <class 'dict'>:{'a': [1, 1, 1, 1, 1]}
            New: <class 'dict'>:{'a': [3, 3]}""")

    dut = A()
    with pytest.raises(TypeNotConsistent) as e:
        dut.main()

    assert str(e.value) == expect


def test_initial_self():
    class A(HW):
        def __init__(self):
            self.a = Sfix(0.0123)
            self.i = 25
            self.b = False

        def main(self):
            self.next.a = Sfix(1.2, 3, -18)
            self.next.i = 0
            self.next.b = True

    dut = A()
    assert dut.a == dut.__dict__['__initial_self__'].a
    assert dut.b == dut.__dict__['__initial_self__'].b
    assert dut.i == dut.__dict__['__initial_self__'].i
    dut.main()
    dut.main()
    dut.main()
    assert dut.__dict__['__initial_self__'].a.init_val == 0.0123
    assert dut.__dict__['__initial_self__'].i == 25
    assert dut.__dict__['__initial_self__'].b == False



def test_decorator_principe():
    class DecoClass:
        def __init__(self, func):
            self.func = func
            self.calls = 0

        def __call__(self, *args):
            self.calls += 1
            return self.func(*args)

        def __get__(self, obj, objtype):
            """Support instance methods."""
            import functools
            return functools.partial(self.__call__, obj)

    class A:
        # @DecoClass
        def main(self):
            pass

    dut1 = A()
    dut1.main = DecoClass(dut1.main)

    dut2 = A()
    dut2.main = DecoClass(dut2.main)


    dut1.main()

    assert dut1.main.calls == 1

    dut2.main()
    dut2.main()
    assert dut1.main.calls == 1
    assert dut2.main.calls == 2


def test_decorator_principe2():
    def tmp(func):
        """ Update register values from "next" """

        @wraps(func)
        def clock_tick_wrap(*args, **kwargs):
            now = args[0].__dict__
            next = args[0].__dict__['next'].__dict__

            ret = func(*args, **kwargs)
            return ret

        clock_tick_wrap.__wrapped__ = clock_tick
        return clock_tick_wrap

    class DecoClass:
        def __init__(self, f):
            self.f = f

        def __call__(self, *args):
            return self.f(*args)

        def __get__(self, obj, objtype):
            """Support instance methods."""
            import functools
            return functools.partial(self.__call__, obj)

    class A:
        def __init__(self):
            self.a = 2

        @tmp
        def main(self, b):
            pass

    class B:
        def __init__(self):
            self.a = 2

        def main(self, b):
            pass

    class C:
        def __init__(self):
            self.a = 2

        @DecoClass
        def main(self, b):
            self.a = b

    # dut1 = A()
    #
    # dut2 = B()
    # dut2.main = tmp(dut2.main)
    #
    #
    # # dut1.main(3)
    # # dut2.main(3)
    #
    dut3 = C()
    dut3.main(123)

    class D:
        def __init__(self):
            self.a = 2

        def main(self, b):
            self.a = b

    dut = D()
    dut.main = DecoClass(dut.main)
    dut.main(321)
    pass
    pass
