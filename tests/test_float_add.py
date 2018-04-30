from math import isclose

import pytest

from pyha import Hardware, simulate, sims_close
from pyha.common.float import Float
import numpy as np

from pyha.simulation.vhdl_simulation import VHDLSimulation


@pytest.mark.parametrize('base', [1, 0, 0.0000432402, 1238893.123, 0.0000000002342, 324788980])
def test_same(base):
    class Dut(Hardware):
        def main(self, a, b):
            r = a + b
            return r

    a = [Float(base), Float(-base), Float(base), Float(-base)]
    b = [Float(base), Float(base), Float(-base), Float(-base)]

    dut = Dut()
    sims = simulate(dut, a, b, simulations=['PYHA', 'RTL'])

    assert sims_close(sims, rtol=1e-9, atol=1e-9)


def test_exponent_overflow():
    pytest.skip('overflows')

    class Dut(Hardware):
        def main(self, a, b):
            r = a + b
            return r

    base = 0.000000000002342
    a = [Float(base), Float(-base), Float(base), Float(-base)]
    b = [Float(base), Float(base), Float(-base), Float(-base)]

    dut = Dut()
    sims = simulate(dut, a, b, simulations=['PYHA', 'RTL'])

    assert sims_close(sims, rtol=1e-9, atol=1e-9)


def test_ones():
    """ Failed due to bug in smaller/bigger logic """

    class Dut(Hardware):
        def main(self, a, b):
            r = a + b
            return r

    base = 1
    a = [Float(-base), Float(base)]
    b = [Float(base), Float(-base)]

    dut = Dut()
    sims = simulate(dut, a, b, simulations=['PYHA', 'RTL'])

    assert sims_close(sims, rtol=1e-9, atol=1e-9)


def test_no_round():
    """ Python side had rounding when converted to Float """

    class Dut(Hardware):
        def main(self, a, b):
            r = a + b
            return r

    a = [Float(0.235351562500000)]
    b = [Float(0.045410156250000)]
    dut = Dut()

    sims = simulate(dut, a, b, simulations=['PYHA',
                                            'RTL',
                                            # 'GATE'
                                            ])
    assert sims_close(sims, rtol=1e-9, atol=1e-9)


def test_no_rr():
    """ Failed on invalid normalization """

    class Dut(Hardware):
        def main(self, a, b):
            r = a + b
            return r

    a = [Float(0.004577636718750)]
    b = [Float(1112.000000000000000)]
    dut = Dut()

    sims = simulate(dut, a, b, simulations=['PYHA',
                                            'RTL',
                                            # 'GATE'
                                            ])
    assert sims_close(sims, rtol=1e-9, atol=1e-9)


def test_no_rrrr():
    """ Failed on invalid normalization """

    class Dut(Hardware):
        def main(self, a, b):
            r = a + b
            return r

    # 001110: 010100110
    a = [Float(6432.000000000000000)]
    b = [Float(4224.000000000000000)]
    dut = Dut()

    sims = simulate(dut, a, b, simulations=['PYHA',
                                            'RTL',
                                            # 'GATE'
                                            ])
    assert sims_close(sims, rtol=1e-9, atol=1e-9)


def test_normalize_grows():
    """ Add grows by one bit """

    class Dut(Hardware):
        def main(self, a, b):
            r = a + b
            return r

    a = [Float(0.990)]
    b = [Float(0.990)]
    dut = Dut()

    sims = simulate(dut, a, b, simulations=['PYHA',
                                            'RTL',
                                            # 'GATE'
                                            ])
    assert sims_close(sims, rtol=1e-9, atol=1e-9)


def test_normalize_no_action():
    """ Result already normalized """

    class Dut(Hardware):
        def main(self, a, b):
            r = a + b
            return r

    a = [Float(0.99)]
    b = [Float(-0.000051)]
    dut = Dut()

    sims = simulate(dut, a, b, simulations=['PYHA',
                                            'RTL',
                                            # 'GATE'
                                            ])
    assert sims_close(sims, rtol=1e-9, atol=1e-9)


def test_normalize_shrink1():
    """ Add shrinks by one bit """

    class Dut(Hardware):
        def main(self, a, b):
            r = a + b
            return r

    a = [Float(0.99), Float(-0.99), Float(-0.98172), Float(0.98172)]
    b = [Float(-0.51), Float(0.51), Float(0.5315), Float(-0.5315)]
    dut = Dut()

    sims = simulate(dut, a, b, simulations=['PYHA',
                                            'RTL',
                                            # 'GATE'
                                            ])
    assert sims_close(sims, rtol=1e-9, atol=1e-9)


def test_normalize_shrink2():
    """ Add shrinks by 2 bit """

    class Dut(Hardware):
        def main(self, a, b):
            r = a + b
            return r

    a = [Float(0.99), Float(-0.99)]
    b = [Float(-0.751), Float(0.751)]
    dut = Dut()

    sims = simulate(dut, a, b, simulations=['PYHA',
                                            'RTL',
                                            # 'GATE'
                                            ])
    assert sims_close(sims, rtol=1e-9, atol=1e-9)


@pytest.mark.parametrize('shrink_bits', [1, 2, 3, 4, 5, 6, 7])
def test_normalize_shrink3(shrink_bits):
    """ Result needs shifting left """

    class Dut(Hardware):
        def main(self, a, b):
            r = a + b
            return r

    low = 1.0 - (2 ** -shrink_bits)
    a = [Float(0.99), Float(-0.99)]
    b = [Float(-low), Float(low)]
    dut = Dut()

    sims = simulate(dut, a, b, simulations=['PYHA',
                                            'RTL',
                                            # 'GATE'
                                            ])
    assert sims_close(sims, rtol=1e-9, atol=1e-9)


def test_normalize_minimal_negative():
    """ Second case is 'negative zero', or minimal negative number """

    shrink_bits = 6

    class Dut(Hardware):
        def main(self, a, b):
            r = a + b
            return r

    low = 1.0 - (2 ** -shrink_bits)
    a = [Float(0.99), Float(-0.99)]
    b = [Float(-low), Float(low)]
    dut = Dut()

    sims = simulate(dut, a, b, simulations=['PYHA',
                                            'RTL',
                                            # 'GATE'
                                            ])
    assert sims_close(sims, rtol=1e-9, atol=1e-9)


# 4: 128

# 5: 139
# 6: 148 (+9)
# 7: 153 (+5)
# 8: 161 (+8)
# 9: 167 (+6)
# 10:173 (+6)
def test_add_resources():
    """ Result already normalized """

    class Dut(Hardware):
        def main(self, a, b):
            r = a + b
            return r

    a = [Float(0.99, 5, 9)]
    b = [Float(-0.000051, 5, 9)]
    dut = Dut()

    sims = simulate(dut, a, b, simulations=['PYHA',
                                            'GATE'
                                            ],
                    conversion_path='/home/gaspar/git/pyha/playground'
                    )
    assert VHDLSimulation.last_logic_elements == 123


def test_add_random():
    class Dut(Hardware):
        def main(self, a, b):
            r = a + b
            return r

    N = 2 ** 15
    gain = 2 ** np.random.uniform(-8, 8, N)
    orig = (np.random.rand(N)) * gain
    a = [Float(x) for x in orig]

    gain = 2 ** np.random.uniform(-8, 8, N)
    orig = (np.random.rand(N)) * gain
    b = [Float(x) for x in orig]
    dut = Dut()

    sims = simulate(dut, a, b, simulations=['PYHA',
                                            'RTL',
                                            # 'GATE'
                                            ])

    assert sims_close(sims, rtol=1e-9, atol=1e-9)


def test_sub_normalize():
    """ Python normalization resulted in X.50, neede to use // instead of / """
    shrink_bits = 6

    class Dut(Hardware):
        def main(self, a, b):
            r = a - b
            return r

    low = 1.0 - (2 ** -shrink_bits)
    # a = [Float(0.99), Float(-0.99)]
    # b = [Float(-low), Float(low)]
    a = [Float(-0.99)]
    b = [Float(low)]
    dut = Dut()

    sims = simulate(dut, a, b, simulations=['PYHA',
                                            'RTL',
                                            # 'GATE'
                                            ])
    assert sims_close(sims, rtol=1e-9, atol=1e-9)


def test_sub_resources():
    """ Result already normalized """

    class Dut(Hardware):
        def main(self, a, b):
            r = a - b
            return r

    a = [Float(0.99, 5, 9)]
    b = [Float(-0.000051, 5, 9)]
    dut = Dut()

    sims = simulate(dut, a, b, simulations=['PYHA',
                                            'GATE'
                                            ],
                    conversion_path='/home/gaspar/git/pyha/playground'
                    )
    assert VHDLSimulation.last_logic_elements == 131


def test_suber():
    """ Bug in - routine """

    class Dut(Hardware):
        def main(self, a, b):
            r = a - b
            return r

    a = [Float(0.000006556510925)]
    b = [Float(2000.000000000000000)]
    dut = Dut()

    sims = simulate(dut, a, b, simulations=['PYHA',
                                            'RTL',
                                            # 'GATE'
                                            ])
    assert sims_close(sims, rtol=1e-9, atol=1e-9)


def test_sub_random():
    class Dut(Hardware):
        def main(self, a, b):
            r = a - b
            return r

    N = 2 ** 15
    gain = 2 ** np.random.uniform(-8, 8, N)
    orig = (np.random.rand(N)) * gain
    a = [Float(x) for x in orig]

    gain = 2 ** np.random.uniform(-8, 8, N)
    orig = (np.random.rand(N)) * gain
    b = [Float(x) for x in orig]
    dut = Dut()

    sims = simulate(dut, a, b, simulations=['PYHA',
                                            'RTL',
                                            # 'GATE'
                                            ])
    assert sims_close(sims, rtol=1e-9, atol=1e-9)


class TestMultiply:
    def test_basic(self):
        class Dut(Hardware):
            def main(self, a, b):
                r = a * b
                return r

        a = [Float(0.1)]
        b = [Float(0.1)]
        dut = Dut()

        sims = simulate(dut, a, b, simulations=['PYHA',
                                                # 'RTL',
                                                'GATE'
                                                ],
                        conversion_path='/home/gaspar/git/pyha/playground'
                        )
        assert sims_close(sims, rtol=1e-9, atol=1e-9)

    def test_random(self):
        class Dut(Hardware):
            def main(self, a, b):
                r = a * b
                return r

        N = 2 ** 10
        gain = 2 ** np.random.uniform(-8, 8, N)
        orig = (np.random.rand(N)) * gain
        a = [Float(x) for x in orig]

        gain = 2 ** np.random.uniform(-8, 8, N)
        orig = (np.random.rand(N)) * gain
        b = [Float(x) for x in orig]
        dut = Dut()

        sims = simulate(dut, a, b, simulations=['PYHA',
                                                'RTL',
                                                # 'GATE'
                                                ])
        assert sims_close(sims, rtol=1e-9, atol=1e-9)

    def test_pyimp_bug1(self):
        a = 1.039062500000000
        b = 0.006103515625000

        expected = a * b
        real = float(Float(a) * Float(b))
        print(real, expected)
        assert isclose(real, expected, rel_tol=1e-6)

    def test_pyimp_bug2(self):
        a = 20.625000000000000
        b = 92.000000000000000

        expected = a * b
        real = float(Float(a) * Float(b))
        print(real, expected)
        assert isclose(real, expected, rel_tol=1e-6)
