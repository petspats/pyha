from pyha.common.hwsim import HW
from pyha.components.blade_demod.bits_decode import DemodToPacket
from pyha.components.blade_demod.blade_demod import BladeDemodQuadMavg


class Phantom2Receiver(HW):
    def __init__(self):
        self.demod = BladeDemodQuadMavg(0.5, 16)
        self.packet = DemodToPacket()

        self._delay = self.demod.get_delay() + self.packet.get_delay()

    def main(self, c):
        demod = self.next.demod.main(c)
        packet_part, valid = self.next.packet.main(demod)
        return packet_part, valid

    def get_delay(self):
        return self._delay

    def model_main(self, c):
        demod = self.demod.model_main(c)
        packet = self.packet.model_main(demod)
        return packet
