import logging
import math

import numpy as np
from pyha.common.context_managers import ContextManagerRefCounted, SimPath

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('sfix')


class Sfix:
    """
    Signed fixed-point type. Default fixed-point format in Pyha is ``Sfix(left=0, right=-17)`` (17 fractional bits + sign)
    , representing values in range [-1, 1] ``(2**0)`` with resolution of 0.0000076 ``(2**-17)``.

    :param val: initial value (reset value in hardware)
    :param left: bits for integer part. Maximum representable value is ``2**left``
    :param right: bits for fractional part. Minimum representable value or resulution is ``2**right``, note that ``right`` is almost always negative number.
    :param overflow_style: 'wrap' (default) or 'saturate'.

        Wrap:

        >>> Sfix(1.25, left=0, right=-17)
        ERROR:sfix:WRAP 1.25000 -> -0.75000	[]
        -0.75 [0:-17]

        Saturation:

        >>> Sfix(1.25, left=0, right=-17, overflow_style='saturate')
        WARNING:sfix:SATURATION 1.25000 -> 0.99999	[]
        0.9999923706054688 [0:-17]


    :param round_style: 'truncate' (default) or 'round'
    :param wrap_is_ok: silences logging about WRAP
    :param init_only: internal use only


    Examples:

    >>> Sfix(0.123, left=0, right=-17)
    0.1230010986328125 [0:-17]
    >>> Sfix(0.123, left=0, right=-7)
    0.125 [0:-7]

    Sfix class can be switched into 'float mode', which disables quantization/saturation/wrap effects.
    This is useful to quickly test your design with full precision.

    >>> with Sfix._float_mode:
    >>>     a = Sfix(0.123123, left=0, right=-7)
    >>> a
    0.123123 [0:-7]

    Arithmetic operations on Sfix values ara always full precision, meaning that they include bit-growth:

    >>> a = Sfix(0.123, left=0, right=-17)
    >>> a
    0.12299346923828125 [0:-17]
    >>> a + a
    0.2459869384765625 [1:-17]
    >>> a + a + a
    0.36898040771484375 [2:-17]
    >>> a * a
    0.015127393475268036 [1:-34]
    >>> a * a * a
    0.0018605706040557557 [2:-51]

    ``resize`` can be used to force values into other format:

    >>> resize(a * a * a, left=0, right=-17)
    0.001861572265625 [0:-17]

    Pyha registers of Sfix type will be automatically resized to initial type on all assignments.

    """

    # Disables all quantization and saturating stuff
    _float_mode = ContextManagerRefCounted()

    def __init__(self, val=0.0, left=None, right=None, overflow_style='wrap',
                 round_style='truncate', init_only=False, wrap_is_ok=False):

        self.wrap_is_ok = wrap_is_ok
        self.round_style = round_style
        self.overflow_style = overflow_style

        val = float(val)

        if isinstance(left, Sfix):
            self.right = left.right
            self.left = left.left
        else:
            self.right = right
            self.left = left

        self.val = val
        self.init_val = val

        if self.left is None or self.right is None:
            return

        assert self.left >= self.right
        # FIXME: This sucks, init should not call these anyways, make to_sfixed function
        if init_only or Sfix._float_mode.enabled:
            return

        if overflow_style is 'saturate':
            if self.overflows():
                self.saturate()
            else:
                self.quantize()
        elif overflow_style in 'wrap':
            self.quantize()
            if self.overflows():
                self.wrap()
        else:
            raise Exception(f'Unknown overflow style {overflow_style}')

    def __eq__(self, other):
        if type(other) is type(self):
            return self.__dict__ == other.__dict__
        return False

    def max_representable(self):
        if self.left < 0:
            # FIXME: I am not sure how to handle this when negative index
            # assert 0

            if self.right == 0:
                return 2 ** self.left
            else:
                return 2 ** self.left - 2 ** self.right
        else:
            return 2 ** self.left - 2 ** self.right

    def min_representable(self):
        return -2 ** self.left

    def overflows(self):
        return self.val < self.min_representable() or \
               self.val > self.max_representable()

    def saturate(self):
        old = self.val
        if self.val > self.max_representable():
            self.val = self.max_representable()
        elif self.val < self.min_representable():
            self.val = self.min_representable()
        else:
            assert False
        if f'{old:.5f}' != f'{self.val:.5f}': # only warn when saturation is significant, TODO: this expects numbers in [1, -1] range!
            if str(SimPath) != 'inputs':
                try:
                    import pydevd
                    pydevd.settrace()
                except ModuleNotFoundError: # this happens when ran in 'Run' mode instead of 'Debug'
                    pass
            logger.warning(f'SATURATION {old:g} -> {self.val:g}\t[{SimPath}]')

    def wrap(self):
        fmin = self.min_representable()
        fmax = 2 ** self.left  # no need to substract minimal step, 0.9998... -> 1.0 will still be wrapped as max bit pattern
        new_val = (self.val - fmin) % (fmax - fmin) + fmin
        if not self.wrap_is_ok:
            if str(SimPath) != 'inputs':
                try:
                    import pydevd
                    pydevd.settrace()
                except ModuleNotFoundError: # this happens when ran in 'Run' mode instead of 'Debug'
                    pass
            logger.error(f'WRAP {self.val:g} -> {new_val:g}\t[{SimPath}]')
        self.val = new_val

    def quantize(self):
        fix = self.val / 2 ** self.right
        if self.round_style is 'round':
            fix = round(fix)
        else:
            # this used to be int(fix), but this is a bug when fix is negative
            fix = math.floor(fix)

        self.val = fix * 2 ** self.right

    # TODO: test, rounding not needed?
    def fixed_value(self):
        return int(round(self.val / 2 ** self.right))

    def __str__(self):
        return f'{self.val:g} [{self.left}:{self.right}]'

    def __repr__(self):
        return self.__str__()

    def __float__(self):
        return float(self.val)

    def __int__(self):
        return int(math.floor(self.val))

    def resize(self, left=0, right=0, type=None, overflow_style='wrap', round_style='truncate', wrap_is_ok=False):
        if type is not None:  # TODO: add tests
            left = type.left
            right = type.right
        return Sfix(self.val, left, right, overflow_style=overflow_style, round_style=round_style, wrap_is_ok=wrap_is_ok)

    def _size_add(self, other):
        """ Size rules for add/sub operation. Handles the 'None'(lazy) cases. """
        if self.left is None and other.left is None:
            left = None
        elif self.left is None:
            left = other.left + 1
        elif other.left is None:
            left = self.left + 1
        else:
            left = max(self.left, other.left) + 1
        if self.right is None and other.right is None:
            right = None
        elif self.right is None:
            right = other.right
        elif other.right is None:
            right = self.right
        else:
            right = min(self.right, other.right)
        return left, right

    def __add__(self, other):
        if type(other) == float:
            other = Sfix(other, self.left, self.right, overflow_style='saturate', round_style='round')

        left, right = self._size_add(other)

        return Sfix(self.val + other.val,
                    left,
                    right,
                    init_only=True)

    def __radd__(self, other):
        return self.__add__(other)

    def __sub__(self, other):
        if type(other) == float:
            other = Sfix(other, self.left, self.right, overflow_style='saturate', round_style='round')

        left, right = self._size_add(other)

        return Sfix(self.val - other.val,
                    left,
                    right,
                    init_only=True)

    def __rsub__(self, other):
        if type(other) == float:
            other = Sfix(other, self.left, self.right, overflow_style='saturate', round_style='round')
        return other.__sub__(self)

    def __mul__(self, other):
        if type(other) == float:
            other = Sfix(other, self.left, self.right, overflow_style='saturate', round_style='round')

        if self.left is None and other.left is None:
            left = None
        elif self.left is None:
            left = other.left + 1
        elif other.left is None:
            left = self.left + 1
        else:
            left = self.left + other.left + 1

        if self.right is None and other.right is None:
            right = None
        elif self.right is None:
            right = other.right
        elif other.right is None:
            right = self.right
        else:
            right = self.right + other.right

        return Sfix(self.val * other.val,
                    left,
                    right,
                    init_only=True)

    def sign_bit(self):
        s = np.sign(self.val)
        if s in [0, 1]:
            return 0
        return 1

    def __rshift__(self, other):
        if self.right is None or Sfix._float_mode.enabled:
            o = math.ldexp(self.val, -other)
        else:
            o = int(self.val / 2 ** self.right)
            o = (o >> other) * 2 ** self.right
        # THIS CAN WRAP!
        return Sfix(o, self.left, self.right)

    def __lshift__(self, other):
        if self.right is None or Sfix._float_mode.enabled:
            o = math.ldexp(self.val, other)
        else:
            o = int(self.val / 2 ** self.right)
            o = (o << other) * 2 ** self.right
        # THIS CAN WRAP!
        return Sfix(o, self.left, self.right)

    def __abs__(self):
        return Sfix(abs(self.val),
                    self.left + 1,
                    self.right,
                    init_only=True)

    def __lt__(self, other):
        return bool(self.val < other)

    def __gt__(self, other):
        return bool(self.val > other)

    def __neg__(self):
        left = None if self.left is None else self.left + 1
        return Sfix(-self.val,
                    left,
                    self.right,
                    init_only=True)

    def __len__(self):
        return -self.right + self.left + 1

    def __call__(self, x: float):
        return Sfix(x, self.left, self.right, self.overflow_style,
                    self.round_style)


# default are 'saturate' and 'round' as this is the case in VHDL lib....
def resize(fix: Sfix, left=0, right=0, size_res=None, overflow_style='wrap', round_style='truncate', wrap_is_ok=False) -> Sfix:
    """
    Resize fixed point number.

    :param fix: Sfix object to resize
    :param left: new left bound
    :param right: new right bound
    :param size_res: provide another Sfix object as size reference
    :param overflow_style: 'wrap' or 'saturate'
    :param round_style: 'truncate' or 'round'
    :param wrap_is_ok: silences logging about WRAP
    :return: New resized Sfix object

    >>> a = Sfix(0.89, left=0, right=-17)
    >>> a
    0.8899993896484375 [0:-17]
    >>> b = resize(a, 0, -6)
    >>> b
    0.890625 [0:-6]

    >>> c = resize(a, size_res=b)
    >>> c
    0.890625 [0:-6]


    """
    if isinstance(fix, (float, int)):
        if size_res is not None:
            left = size_res.left
            right = size_res.right
        return Sfix(fix, left, right, overflow_style=overflow_style, round_style=round_style, wrap_is_ok=wrap_is_ok)

    return fix.resize(left, right, size_res, overflow_style=overflow_style, round_style=round_style, wrap_is_ok=wrap_is_ok)


def left_index(x: Sfix) -> int:
    """

    :return: left bound

    >>> a = Sfix(-0.5, 1, -7)
    >>> left_index(a)
    1

    """
    return x.left


def right_index(x: Sfix) -> int:
    """

    :return: right bound

    >>> a = Sfix(-0.5, 1, -7)
    >>> right_index(a)
    -7
    """
    return x.right


def scalb(x: Sfix, i: int) -> Sfix:
    """
    This is like ``>>``/``<<``, but without precision loss i.e. it changes the fixed-point format.

    >>> a = Sfix(0.5, 0, -17)
    >>> a
    0.5 [0:-17]
    >>> scalb(a, 8)
    128.0 [8:-9]
    >>> scalb(a, -8)
    0.001953125 [-8:-25]
    """
    n = 2 ** i
    return Sfix(x.val * n, x.left + i, x.right + i, overflow_style='saturate', round_style='round')


default_sfix = Sfix(0, 0, -17, overflow_style='saturate',
                    round_style='round')