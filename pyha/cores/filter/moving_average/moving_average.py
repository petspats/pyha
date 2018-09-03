import numpy as np
import pytest
from scipy import signal

from pyha import Hardware, Sfix, simulate, sims_close, Complex, scalb
from pyha.common.fixed_point import sign_bit
from pyha.common.shift_register import ShiftRegister
from pyha.cores import DataValidToNumpy, NumpyToDataValid, DownCounter
from pyha.cores.fft.packager.packager import DataValid


class MovingAverage(Hardware):
    """
    :param window_len: Size of the moving average window, must be power of 2 and >= 2
    :param dtype: internal storage type, Sfix/Complex
    """

    def __init__(self, window_len, dtype=Sfix):
        self._pyha_simulation_input_callback = NumpyToDataValid(
            dtype=dtype(0.0, 0, -17, overflow_style='saturate', round_style='round'))
        self._pyha_simulation_output_callback = DataValidToNumpy()
        self.WINDOW_LEN = window_len
        self.BIT_GROWTH = int(np.log2(window_len))
        self.DELAY = 2

        self.shr = ShiftRegister([dtype()] * self.WINDOW_LEN)
        self.acc = dtype(0.0, self.BIT_GROWTH, -17)

        # rounding the output is necessary or there will be negative trend!
        self.out = DataValid(dtype(0, 0, -17, round_style='round'), valid=False)
        self.final_counter = DownCounter(1)
        self.start_counter = DownCounter(1)
        # self.flushing = False

    def main(self, inp):
        # if self.flushing:
        #     self.final_counter.main()
        #
        # if inp.valid:
        #     self.start_counter.main()
        #
        # if inp.final and not self.flushing:
        #     self.flushing = True
        #     self.final_counter.restart()
        #
        # if self.flushing and self.final_counter.is_over():
        #     self.flushing = False
        #     self.start_counter.restart()
        #     self.final_counter.restart()
        #     self.shr = ShiftRegister([Complex()] * self.WINDOW_LEN)
        #     self.acc = Complex(0.0, self.BIT_GROWTH, -17)
        #     # return DataValid(self.out.data, valid=False, final=True)
        #
        # elif not inp.valid and not self.flushing:
        #     return DataValid(self.out.data, valid=False, final=False)


        if inp.final:
            self.final_counter.main()
        else:
            if not inp.valid:
                return DataValid(self.out.data, valid=False, final=False)
            self.final_counter.restart()
            self.start_counter.main()


        self.shr.push_next(inp.data)  # add new element to shift register
        self.acc = self.acc + inp.data - self.shr.peek()

        self.out.data = scalb(self.acc, -self.BIT_GROWTH)
        self.out.valid = self.start_counter.is_over()
        self.out.final = self.final_counter.is_over()
        return self.out

    def model_main(self, inputs):
        # https://stackoverflow.com/questions/13728392/moving-average-or-running-mean/27681394#27681394
        # can be expressed as FIR filter with special taps:

        taps = [1 / self.WINDOW_LEN] * self.WINDOW_LEN
        return signal.lfilter(taps, [1.0], inputs)

        taps = np.ones(self.WINDOW_LEN)/self.WINDOW_LEN
        return np.convolve(inputs, taps, mode='same')


@pytest.mark.parametrize("window_len", [2])
@pytest.mark.parametrize("input_power", [0.25])
@pytest.mark.parametrize("dtype", [Complex])
def test_lolz(window_len, input_power, dtype):
    np.random.seed(0)
    dut = MovingAverage(window_len=window_len, dtype=dtype)
    N = 4
    if dtype == Complex:
        input_signal = (np.random.normal(size=N) + np.random.normal(size=N) * 1j)
    else:
        input_signal = np.random.normal(size=N)

    input_signal *= input_power

    sim_out = simulate(dut, input_signal, simulations=['MODEL', 'PYHA'])
    assert sims_close(sim_out)

    sim_out = simulate(dut, input_signal, simulations=['MODEL', 'PYHA'])
    assert sims_close(sim_out)


@pytest.mark.parametrize("window_len", [2, 4, 8, 16, 32])
@pytest.mark.parametrize("input_power", [0.25, 0.001])
@pytest.mark.parametrize("dtype", [Sfix, Complex])
def test_all(window_len, input_power, dtype):
    # TODO: Quantize shit...and find rtol, atol
    np.random.seed(0)
    dut = MovingAverage(window_len=window_len, dtype=dtype)
    N = 128
    if dtype == Complex:
        input_signal = (np.random.normal(size=N) + np.random.normal(size=N) * 1j)
    else:
        input_signal = np.random.normal(size=N)

    input_signal *= input_power

    sim_out = simulate(dut, input_signal, simulations=['MODEL', 'PYHA'])
    assert sims_close(sim_out)