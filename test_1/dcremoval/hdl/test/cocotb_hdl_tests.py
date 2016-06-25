# Simple tests for an adder module
import cocotb
import numpy as np
from cocotb.clock import Clock
from cocotb.result import ReturnValue
from cocotb.triggers import RisingEdge, Timer, FallingEdge

from common.sfix import Sfix
from common.sfixed import to_sfixed_real, to_real
from test_1.dcremoval.dcrem import DCRemoval


@cocotb.coroutine
def reset(dut, duration=10000):
    dut.log.debug("Resetting DUT")
    dut.rst_n = 0
    yield Timer(duration)
    yield RisingEdge(dut.clk)
    dut.rst_n = 1
    dut.log.debug("Out of reset")


@cocotb.coroutine
def run_dut(dut, x1, x2, data_width):
    cocotb.fork(Clock(dut.clk, 5000).start())
    yield reset(dut)

    x1 = np.copy(x1)
    x1 = to_sfixed_real(x1, data_width)

    x2 = np.copy(x2)
    x2 = to_sfixed_real(x2, data_width)

    y1 = []
    y2 = []
    for xi1, xi2 in zip(x1, x2):
        dut.x1 = xi1.astype(int)
        dut.x2 = xi2.astype(int)
        # FIXME: NOTICE, need to have both yields to match simulation.
        yield RisingEdge(dut.clk)
        yield FallingEdge(dut.clk)
        y1.append(float(dut.y1.value.signed_integer))
        y2.append(float(dut.y2.value.signed_integer))

    y1 = to_real(np.array(y1), data_width)
    y2 = to_real(np.array(y2), data_width)

    # plt.plot(y1)
    # plt.plot(y2)
    # plt.show()
    raise ReturnValue((y1, y2))


@cocotb.coroutine
def link_to_model(dut, x1, x2):
    cocotb.fork(Clock(dut.clk, 5000).start())
    yield reset(dut)

    av = DCRemoval(4, 2)

    rl = [av.main(Sfix(xi1, 0, -17), Sfix(xi2, 0, -17)) for xi1, xi2 in zip(x1, x2)]
    ri, rq = zip(*rl)
    ri = [float(x) for x in ri]
    rq = [float(x) for x in rq]
    # plt.plot(ri)
    # plt.plot(rq)
    # plt.show()
    # av = Casc(4, 2)
    # model_out = [float(av.main(Sfix(x, 0, -17))) for x in input]

    hdl_out = yield run_dut(dut, x1, x2, 18)

    # plt.plot(ri)
    # plt.plot(hdl_out[0])
    # plt.show()

    np.testing.assert_almost_equal(hdl_out[0], ri)
    np.testing.assert_almost_equal(hdl_out[1], rq)
    # if (model_out != hdl_out).any():
    #     raise TestFailure()


@cocotb.test()
def test_main(dut):
    x1 = np.random.uniform(-1, 1, 64)
    x2 = np.random.uniform(-1, 1, 64)
    yield link_to_model(dut, x1, x2)

# @cocotb.test()
# def test_pos_avg(dut):
#     """ DUT gives the same avg when inputs positive """
#     x = [i for i in range(128)]
#     yield link_to_model(dut, x)
#
#
# @cocotb.test()
# def test_neg_avg(dut):
#     """ DUT gives the same avg when inputs negative """
#     x = [i for i in range(0, -128, -1)]
#     yield link_to_model(dut, x)
#
#
# @cocotb.test()
# def test_pos_sum_overflow(dut):
#     """ DUT should never overflow +SUM """
#     windowPow = int(os.environ['GENERIC_WINDOW_POW'])
#     dataWidth = int(os.environ['GENERIC_DATA_WIDTH'])
#
#     maxElems = 2 ** windowPow
#     maxInput = (2 ** (dataWidth - 1)) - 1
#     x = [maxInput for _ in range(maxElems + 10)]
#
#     yield link_to_model(dut, x)
#
#
# @cocotb.test()
# def test_neg_sum_overflow(dut):
#     """ DUT should never overflow -SUM """
#     windowPow = int(os.environ['GENERIC_WINDOW_POW'])
#     dataWidth = int(os.environ['GENERIC_DATA_WIDTH'])
#
#     maxElems = 2 ** windowPow
#     minInput = (2 ** (dataWidth - 1))
#     x = [-minInput for _ in range(maxElems + 10)]
#
#     yield link_to_model(dut, x)
#
#
# @cocotb.test()
# def test_sin(dut):
#     """ Sine input, DUT matches model """
#     x = 1024 * np.sin(2 * np.pi * 10 * np.arange(256) / float(60))
#     x = x.astype(int)
#     yield link_to_model(dut, x)
