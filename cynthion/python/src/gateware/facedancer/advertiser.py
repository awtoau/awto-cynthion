#
# This file is part of Cynthion.
#
# Copyright (c) 2024 Great Scott Gadgets <info@greatscottgadgets.com>
# SPDX-License-Identifier: BSD-3-Clause

from types import SimpleNamespace

from amaranth                      import *
from amaranth.lib                  import wiring
from amaranth.lib.wiring           import In, flipped, connect

from amaranth_soc  import csr


class UartTx(Elaboratable):
    """Minimal 8-N-1 UART transmitter with ready/valid handshake."""

    def __init__(self, divisor):
        self.divisor = max(1, int(divisor))

        self.data  = Signal(8)
        self.valid = Signal()
        self.ready = Signal()
        self.tx    = Signal(init=1)

    def elaborate(self, platform):
        m = Module()

        shift_reg = Signal(10, init=0x3FF)
        bit_count = Signal(range(11), init=0)
        divisor   = Signal(range(self.divisor), init=0)
        active    = Signal(init=0)

        m.d.comb += [
            self.ready.eq(~active),
            self.tx.eq(Mux(active, shift_reg[0], 1)),
        ]

        with m.If(active):
            with m.If(divisor == self.divisor - 1):
                m.d.sync += divisor.eq(0)

                with m.If(bit_count == 1):
                    m.d.sync += active.eq(0)
                    m.d.sync += bit_count.eq(0)
                    m.d.sync += shift_reg.eq(0x3FF)
                with m.Else():
                    m.d.sync += bit_count.eq(bit_count - 1)
                    m.d.sync += shift_reg.eq(Cat(shift_reg[1:], Const(1, 1)))
            with m.Else():
                m.d.sync += divisor.eq(divisor + 1)

        with m.Elif(self.valid):
            # Frame is {stop=1, data[7:0], start=0}; line sends LSB first.
            m.d.sync += shift_reg.eq(Cat(Const(0, 1), self.data, Const(1, 1)))
            m.d.sync += bit_count.eq(10)
            m.d.sync += divisor.eq(0)
            m.d.sync += active.eq(1)

        return m


class PatternUartStreamer(Elaboratable):
    """Streams C1 14 01 A5 on UART at a fixed interval when enabled."""

    PATTERN = (0xC1, 0x14, 0x01, 0xA5)

    def __init__(self, pad=None, clk_freq_hz=None, baud_rate=1_000_000, period_ms=100):
        if pad is None:
            pad = SimpleNamespace(o=Signal(init=1))

        self.pad         = pad
        self.clk_freq_hz = clk_freq_hz
        self.baud_rate   = baud_rate
        self.period_ms   = period_ms
        self.stop        = Signal()

    def elaborate(self, platform):
        m = Module()

        # Handle defaults.
        if self.pad is None and platform is not None:
            self.pad = platform.request("int")
        if self.clk_freq_hz is None:
            self.clk_freq_hz = int(platform.DEFAULT_CLOCK_FREQUENCIES_MHZ["sync"] * 1e6)

        divisor = max(1, int(round(self.clk_freq_hz / self.baud_rate)))
        burst_gap_cycles = max(1, int(self.clk_freq_hz * (self.period_ms / 1000.0)))

        m.submodules.uart_tx = uart_tx = UartTx(divisor=divisor)

        wait_cycles = Signal(range(burst_gap_cycles), init=0)
        byte_index  = Signal(range(len(self.PATTERN)), init=0)
        sending     = Signal(init=1)

        current_byte = Array(Const(value, 8) for value in self.PATTERN)

        m.d.comb += [
            self.pad.o.eq(uart_tx.tx),
            uart_tx.valid.eq(0),
            uart_tx.data.eq(current_byte[byte_index]),
        ]

        with m.If(self.stop):
            m.d.sync += sending.eq(1)
            m.d.sync += wait_cycles.eq(0)
            m.d.sync += byte_index.eq(0)
        with m.Else():
            with m.If(sending):
                m.d.comb += uart_tx.valid.eq(uart_tx.ready)
                with m.If(uart_tx.ready):
                    with m.If(byte_index == len(self.PATTERN) - 1):
                        m.d.sync += byte_index.eq(0)
                        m.d.sync += sending.eq(0)
                        m.d.sync += wait_cycles.eq(0)
                    with m.Else():
                        m.d.sync += byte_index.eq(byte_index + 1)
            with m.Else():
                with m.If(wait_cycles == burst_gap_cycles - 1):
                    m.d.sync += sending.eq(1)
                    m.d.sync += wait_cycles.eq(0)
                with m.Else():
                    m.d.sync += wait_cycles.eq(wait_cycles + 1)

        return m


class Peripheral(wiring.Component):
    """Controller peripheral for FPGA_ADV sideband UART streamer."""

    class Control(csr.Register, access="w"):
        """Control register

            enable : Set this bit to '1' to start ApolloAdvertiser and disconnect the
                     Cynthion USB control port from Apollo.
        """
        def __init__(self):
            super().__init__({
                "enable": csr.Field(csr.action.W, unsigned(1)),
            })


    def __init__(self, pad=None, clk_freq_hz=None):
        # Sideband UART streamer on FPGA_ADV.
        self.streamer = PatternUartStreamer(pad=pad, clk_freq_hz=clk_freq_hz)

        # registers
        regs = csr.Builder(addr_width=1, data_width=8)
        self._control = regs.add("control", self.Control())

        # bridge
        self._bridge = csr.Bridge(regs.as_memory_map())

        # bus
        super().__init__({
            "bus" : In(self._bridge.bus.signature),
        })
        self.bus.memory_map = self._bridge.bus.memory_map


    def elaborate(self, platform):
        m = Module()
        m.submodules += self._bridge

        # bus
        connect(m, self.bus, self._bridge.bus)

        # Streaming is disabled by default.
        stop = Signal(init=1)

        # Update streamer stop signal on register write.
        with m.If(self._control.f.enable.w_stb):
            m.d.sync += stop.eq(~self._control.f.enable.w_data)

        # Sideband streamer.
        m.submodules.streamer = self.streamer
        m.d.comb += self.streamer.stop.eq(stop)

        return m
