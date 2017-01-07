import textwrap
from pathlib import Path

import pytest

from pyha.common.hwsim import HW
from pyha.common.sfix import Sfix, ComplexSfix
from pyha.conversion.conversion import get_conversion, Conversion
from pyha.conversion.extract_datamodel import DataModel
from pyha.conversion.top_generator import TopGenerator
from pyha.simulation.simulation_interface import assert_sim_match, SIM_HW_MODEL, SIM_RTL, SIM_GATE


def test_py_implementation():
    a = ComplexSfix()
    assert a.real == Sfix(0.0, 0, 0, overflow_style='SATURATE')
    assert a.imag == Sfix(0.0, 0, 0, overflow_style='SATURATE')

    a = ComplexSfix(0)
    assert a.real == Sfix(0.0, 0, 0, overflow_style='SATURATE')
    assert a.imag == Sfix(0.0, 0, 0, overflow_style='SATURATE')

    a = ComplexSfix(0.5 + 1.2j, 1, -12)
    assert a.real == Sfix(0.5, 1, -12, overflow_style='SATURATE')
    assert a.imag == Sfix(1.2, 1, -12, overflow_style='SATURATE')

    a = ComplexSfix(0.699 + 0.012j, 0, -4)
    assert a.real.val == 0.6875
    assert a.imag.val == 0
    assert a.init_val == 0.699 + 0.012j
    assert a.left == 0
    assert a.right == -4


def test_fixed_value():
    a = ComplexSfix(1 + 0.5j, 0, -2)
    assert a.real.val == 0.75  # quantized
    assert a.real.fixed_value() == 3

    assert a.imag.val == 0.5
    assert a.imag.fixed_value() == 2
    r = a.fixed_value()
    assert r == 26


def test_fixed_value2():
    a = ComplexSfix(1 + 1.95j, 1, -16)
    assert a.real.val == 1.0
    assert a.real.fixed_value() == 65536

    assert a.imag.val == 1.9499969482421875
    assert a.imag.fixed_value() == 127795
    r = a.fixed_value()
    assert r == 17179996979


def test_fixed_value3():
    a = ComplexSfix(-1 - 0.5j, 0, -2)
    assert a.real.val == -1
    assert a.real.fixed_value() == -4

    assert a.imag.val == -0.5
    assert a.imag.fixed_value() == -2
    r = a.fixed_value()
    assert r == -26


def test_fixed_value_too_large_bitwidth():
    a = ComplexSfix(1 + 1.95j, 16, -16)
    with pytest.raises(AssertionError):
        a.fixed_value()


@pytest.fixture
def reg():
    class A(HW):
        def __init__(self):
            self.reg = ComplexSfix(0.5 + 1.2j, 1, -12)

        def main(self, x):
            self.next.reg = x
            return self.reg

    dut = A()
    dut.main(ComplexSfix(0.5 + 1.2j, 1, -12))
    dut.main(ComplexSfix(0.5 + 1.2j, 1, -12))
    return dut


def test_reg_datamodel(reg):
    datamodel = DataModel(reg)
    assert datamodel.locals['main']['x'] == ComplexSfix(0.5 + 1.2j, 1, -12)
    assert datamodel.self_data['reg'] == ComplexSfix(0.5 + 1.2j, 1, -12)


def test_reg_conversion_datamodel(reg):
    conv = get_conversion(reg)

    expect = textwrap.dedent("""\
            type register_t is record
                reg: complex_sfix1_12;
            end record;

            type self_t is record
                reg: complex_sfix1_12;
                \\next\\: register_t;
            end record;""")
    dm = conv.get_datamodel()
    assert expect == dm


def test_reg_conversion_reset(reg):
    conv = get_conversion(reg)

    expect = textwrap.dedent("""\
        procedure reset(self_reg: inout register_t) is
        begin
            self_reg.reg := (real=>to_sfixed(0.5, 1, -12), imag=>to_sfixed(1.2, 1, -12));
        end procedure;""")

    assert expect == str(conv.get_reset_str())


def test_reg_conversion_top_entity(reg):
    dut = reg
    res = TopGenerator(dut)
    # input
    assert 'in0: in std_logic_vector(27 downto 0);' == res.make_entity_inputs()
    assert 'variable var_in0: complex_sfix1_12;' == res.make_input_variables()
    assert 'var_in0 := ' \
           '(real=>to_sfixed(in0(27 downto 14), 1, -12), imag=>to_sfixed(in0(13 downto 0), 1, -12));' \
           == res.make_input_type_conversions()

    # output
    assert 'out0: out std_logic_vector(27 downto 0);' == res.make_entity_outputs()
    assert 'variable var_out0: complex_sfix1_12;' == res.make_output_variables()
    assert 'out0 <= to_slv(var_out0.real) & to_slv(var_out0.imag);' == res.make_output_type_conversions()


def test_reg_complex_types_generation(reg):
    conv = Conversion(reg)
    expect = textwrap.dedent("""\
        library ieee;
            use ieee.fixed_pkg.all;

        package ComplexTypes is
        type complex_sfix1_12 is record
            real: sfixed(1 downto -12);
            imag: sfixed(1 downto -12);
        end record;
        end package;""")

    files = conv.write_vhdl_files(Path('/tmp/'))
    with files[0].open('r') as f:
        assert expect == f.read()


def test_reg_simulate(reg):
    dut = reg
    x = [0.5 + 0.1j, 0.5 - 0.09j, -0.5 + 0.1j, 0.14 + 0.1j, 0.5 + 0.89j]
    expected = [0.5 + 1.2j, 0.5 + 0.1j, 0.5 - 0.09j, -0.5 + 0.1j, 0.14 + 0.1j]

    assert_sim_match(dut, [ComplexSfix(left=1, right=-12)], expected, x, rtol=1e-3,
                     simulations=[SIM_HW_MODEL, SIM_RTL])


@pytest.fixture
def shr():
    class A1(HW):
        def __init__(self):
            self.reg = [ComplexSfix(0.5 + 1.2j, 1, -18), ComplexSfix(0.5 + 0.2j, 1, -18),
                        ComplexSfix(0.1 + 1.2j, 1, -18), ComplexSfix(0.2 - 1.2j, 1, -18)]

        def main(self, x):
            self.next.reg = [x] + self.reg[:-1]
            return self.reg[-1]

    dut = A1()
    dut.main(ComplexSfix(0.5 + 1.2j, 1, -18))
    dut.main(ComplexSfix(0.5 + 1.2j, 1, -18))
    return dut


def test_shr_conversion_reset(shr):
    conv = get_conversion(shr)

    expect = textwrap.dedent("""\
        procedure reset(self_reg: inout register_t) is
        begin
            self_reg.reg := ((real=>to_sfixed(0.5, 1, -18), imag=>to_sfixed(1.2, 1, -18)), (real=>to_sfixed(0.5, 1, -18), imag=>to_sfixed(0.2, 1, -18)), (real=>to_sfixed(0.1, 1, -18), imag=>to_sfixed(1.2, 1, -18)), (real=>to_sfixed(0.2, 1, -18), imag=>to_sfixed(-1.2, 1, -18)));
        end procedure;""")

    assert expect == str(conv.get_reset_str())


def test_shr_simulate(shr):
    dut = shr
    x = [0.5 + 0.1j, 0.5 - 0.09j, -0.5 + 0.1j, 0.14 + 0.1j, 0.5 + 0.89j]
    expected = [0.200001 - 1.200001j, 0.099998 + 1.200001j, 0.500000 + 0.200001j,
                0.500000 + 1.200001j, 0.500000 + 0.099998j]

    assert_sim_match(dut, [ComplexSfix(left=1, right=-18)], expected, x, rtol=1e-3,
                     simulations=[SIM_HW_MODEL, SIM_RTL])


@pytest.fixture
def more_regs():
    class A3(HW):
        def __init__(self):
            self.reg0 = ComplexSfix(0.5 + 1.2j, 1, -12)
            self.reg1 = ComplexSfix(0.5 + 1.2j, 1, -21)
            self.reg2 = ComplexSfix(0.68 - 0.987j, 1, -12)

        def main(self, x0, x1, x2):
            self.next.reg0 = x0
            self.next.reg1 = x1
            self.next.reg2 = x2
            return self.reg0, self.reg1, self.reg2

    dut = A3()
    dut.main(ComplexSfix(0.5 + 1.2j, 1, -12), ComplexSfix(0.5 + 1.2j, 1, -12), ComplexSfix(0.5 + 1.2j, 1, -21))
    dut.main(ComplexSfix(0.5 + 1.2j, 1, -12), ComplexSfix(0.5 + 1.2j, 1, -12), ComplexSfix(0.5 + 1.2j, 1, -21))
    return dut


def test_more_regs_complex_types_generation(more_regs):
    conv = Conversion(more_regs)
    expect = textwrap.dedent("""\
            library ieee;
                use ieee.fixed_pkg.all;

            package ComplexTypes is
            type complex_sfix1_12 is record
                real: sfixed(1 downto -12);
                imag: sfixed(1 downto -12);
            end record;
            type complex_sfix1_21 is record
                real: sfixed(1 downto -21);
                imag: sfixed(1 downto -21);
            end record;
            end package;""")

    files = conv.write_vhdl_files(Path('/tmp/'))
    with files[0].open('r') as f:
        assert expect == f.read()

def test_more_regs_simulate(more_regs):
    dut = more_regs
    x = [[0.5 + 0.1j, 0.5 + 0.1j, 0.5 + 0.1j],
         [0.5 - 0.09j, 0.5 - 0.09j, 0.5 - 0.09j],
         [-0.5 + 0.1j, -0.5 + 0.1j, -0.5 + 0.1j]]
    expected = [[0.500000 + 1.199951j, 0.500000 + 0.100098j, 0.500000 + 0.100098j],
                [0.500000 + 1.2j, 0.500000 - 0.090088j, 0.500000 - 0.090088j],
                [0.679932 - 0.987061j, -0.500000 + 0.1j, -0.500000 + 0.1j]]

    assert_sim_match(dut,
                     [ComplexSfix(left=1, right=-12), ComplexSfix(left=1, right=-21), ComplexSfix(left=1, right=-12)],
                     expected, *x, rtol=1e-3,
                     simulations=[SIM_HW_MODEL, SIM_RTL, SIM_GATE])