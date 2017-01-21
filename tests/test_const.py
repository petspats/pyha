import textwrap

from pyha.common.const import Const
from pyha.common.hwsim import HW
from pyha.conversion.conversion import get_conversion
from pyha.conversion.extract_datamodel import DataModel


class TestSingleInt:
    def setup(self):
        class T0(HW):
            def __init__(self):
                self.mode = Const(1)

            def main(self, a):
                if a:
                    return a
                else:
                    return 0

        self.dut = T0()
        self.dut.main(1)
        self.dut.main(2)

    def test_datamodel(self):
        datamodel = DataModel(self.dut)
        assert datamodel.self_data['much_dummy_very_wow'] == 0  # dummy because constants are not added to VHDL self
        assert datamodel.constants['mode'] == Const(1)

    def test_vhdl_datamodel(self):
        conv = get_conversion(self.dut)

        expect = textwrap.dedent("""\
                type register_t is record
                    much_dummy_very_wow: integer;
                end record;

                type self_t is record
                    -- constants
                    mode: integer;

                    much_dummy_very_wow: integer;
                    \\next\\: register_t;
                end record;""")
        dm = conv.get_datamodel()
        assert expect == dm

    def test_vhdl_reset(self):
        conv = get_conversion(self.dut)

        expect = textwrap.dedent("""\
            procedure reset(self_reg: inout register_t) is
            begin
                self_reg.much_dummy_very_wow := 0;
            end procedure;""")

        assert expect == str(conv.get_reset_str())




        # todo: for lists of submodules constants must match!
