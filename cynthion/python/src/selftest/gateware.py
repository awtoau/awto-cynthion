#!/usr/bin/env python3
#
# This file is part of Cynthion.
#
# Copyright (c) 2020-2024 Great Scott Gadgets <info@greatscottgadgets.com>
# SPDX-License-Identifier: BSD-3-Clause

from amaranth import Signal, Elaboratable, Module, Cat, Mux, ClockDomain, ClockSignal, ResetSignal
from amaranth.lib.cdc import FFSynchronizer

from luna.gateware.architecture.car   import LunaECP5DomainGenerator
from luna.gateware.interface.jtag     import JTAGRegisterInterface
from luna.gateware.interface.ulpi     import ULPIRegisterWindow
from luna.gateware.interface.psram    import HyperRAMPHY, HyperRAMInterface

from .registers import *


CLOCK_FREQUENCIES = {
    "fast": 60,
    "sync": 60,
    "usb":  60
}

# Animation timebase for the LED test modes.
#
# The sync domain runs at 60 MHz. We divide it down to a ~1 kHz base tick, then
# divide that again by (led_speed + 1) to get the animation step rate. That puts
# the default (speed 100) at roughly 10 steps/second -- fast enough to look like
# motion, slow enough for a person to count the LEDs and spot a dead one.
SYNC_HZ            = CLOCK_FREQUENCIES["sync"] * 1_000_000
BASE_TICK_HZ       = 1000
BASE_TICK_DIVISOR  = SYNC_HZ // BASE_TICK_HZ
DEFAULT_LED_SPEED  = 100


class SelftestDevice(Elaboratable):

    def elaborate(self, platform):
        m = Module()

        # Generate our clock domains.
        clocking = LunaECP5DomainGenerator(clock_frequencies=CLOCK_FREQUENCIES)
        m.submodules.clocking = clocking

        registers = JTAGRegisterInterface(default_read_value=0xDEADBEEF)
        m.submodules.registers = registers

        # Simple applet ID register.
        registers.add_read_only_register(REGISTER_ID, read=0x54455354)

        # LED test register.
        led_reg = registers.add_register(REGISTER_LEDS, size=6, name="leds", init=0b111111)
        led_out   = Cat([platform.request("led", i, dir="o").o for i in range(0, 6)])

        # LED test modes: REGISTER_LEDS still drives the LEDs directly in the default
        # static mode, so existing host-side tests are unaffected.
        led_mode  = registers.add_register(REGISTER_LED_MODE,  size=3, name="led_mode",  init=LED_MODE_STATIC)
        led_speed = registers.add_register(REGISTER_LED_SPEED, size=8, name="led_speed", init=DEFAULT_LED_SPEED)
        m.d.comb += led_out.eq(self.led_animator(m, led_reg, led_mode, led_speed))

        #
        # ULPI PHY windows
        #
        self.add_ulpi_registers(m, platform,
            ulpi_bus="target_phy",
            register_base=REGISTER_TARGET_ADDR
        )
        self.add_ulpi_registers(m, platform,
            ulpi_bus="aux_phy" if platform.version >= (0, 6) else "host_phy",
            register_base=REGISTER_AUX_ADDR
        )
        self.add_ulpi_registers(m, platform,
            ulpi_bus="control_phy" if platform.version >= (0, 6) else "sideband_phy",
            register_base=REGISTER_CONTROL_ADDR
        )


        #
        # HyperRAM test connections.
        #
        ram_bus = platform.request('ram')
        psram_phy = HyperRAMPHY(bus=ram_bus)
        psram = HyperRAMInterface(phy=psram_phy.phy)
        m.submodules += [psram_phy, psram]

        psram_address_changed = Signal()
        psram_address = registers.add_register(REGISTER_RAM_REG_ADDR, write_strobe=psram_address_changed)

        # Store last read word from HyperRAM.
        psram_read_data = Signal.like(psram.read_data)
        with m.If(psram.read_ready):
            m.d.sync += psram_read_data.eq(psram.read_data)
        registers.add_sfr(REGISTER_RAM_VALUE, read=psram_read_data)

        # Hook up our PSRAM.
        m.d.comb += [
            ram_bus.reset.o        .eq(0),
            psram.single_page      .eq(0),
            psram.perform_write    .eq(0),
            psram.register_space   .eq(1),
            psram.final_word       .eq(1),
            psram.start_transfer   .eq(psram_address_changed),
            psram.address          .eq(psram_address),
        ]

        return m


    def led_animator(self, m, led_reg, led_mode, led_speed):
        """ Builds the LED test-mode animator.

        Returns a 6-bit signal to drive the LEDs. In LED_MODE_STATIC this is just
        led_reg, so the register keeps its original write-and-read-back behaviour;
        the other modes ignore led_reg and animate on their own.
        """

        # Divide the sync domain down to the base tick.
        base_counter = Signal(range(BASE_TICK_DIVISOR))
        base_tick    = Signal()
        m.d.comb += base_tick.eq(base_counter == 0)
        with m.If(base_tick):
            m.d.sync += base_counter.eq(BASE_TICK_DIVISOR - 1)
        with m.Else():
            m.d.sync += base_counter.eq(base_counter - 1)

        # Divide the base tick by (led_speed + 1) to get the animation step.
        # The +1 means speed 0 is the fastest setting rather than a stopped animation.
        step_counter = Signal.like(led_speed)
        step         = Signal()
        m.d.comb += step.eq(base_tick & (step_counter == 0))
        with m.If(base_tick):
            with m.If(step_counter == 0):
                m.d.sync += step_counter.eq(led_speed)
            with m.Else():
                m.d.sync += step_counter.eq(step_counter - 1)

        # Animation state, advanced once per step.
        chase_pos = Signal(range(6))    # wrapping position, for chase
        bounce_pos = Signal(range(6))   # reversing position, for bounce
        ascending = Signal(init=1)      # bounce direction
        counter   = Signal(6)           # free-running, for blink/count/bar

        with m.If(step):
            m.d.sync += counter.eq(counter + 1)

            # Chase wraps back to LED0 after the top.
            with m.If(chase_pos == 5):
                m.d.sync += chase_pos.eq(0)
            with m.Else():
                m.d.sync += chase_pos.eq(chase_pos + 1)

            # Bounce reverses at each end instead of wrapping.
            with m.If(ascending):
                with m.If(bounce_pos == 5):
                    m.d.sync += [bounce_pos.eq(4), ascending.eq(0)]
                with m.Else():
                    m.d.sync += bounce_pos.eq(bounce_pos + 1)
            with m.Else():
                with m.If(bounce_pos == 0):
                    m.d.sync += [bounce_pos.eq(1), ascending.eq(1)]
                with m.Else():
                    m.d.sync += bounce_pos.eq(bounce_pos - 1)

        # Bar level: counter's low bits ramp 0..5, then the bar empties.
        bar = Signal(6)
        with m.Switch(counter[:3]):
            for level in range(6):
                with m.Case(level):
                    m.d.comb += bar.eq((1 << (level + 1)) - 1)
            with m.Default():
                m.d.comb += bar.eq(0)

        leds = Signal(6)
        with m.Switch(led_mode):
            with m.Case(LED_MODE_CHASE):
                m.d.comb += leds.eq(1 << chase_pos)
            with m.Case(LED_MODE_BOUNCE):
                m.d.comb += leds.eq(1 << bounce_pos)
            with m.Case(LED_MODE_BLINK):
                m.d.comb += leds.eq(Mux(counter[0], 0b111111, 0b000000))
            with m.Case(LED_MODE_COUNT_UP):
                m.d.comb += leds.eq(counter)
            with m.Case(LED_MODE_BAR):
                m.d.comb += leds.eq(bar)
            with m.Default():   # LED_MODE_STATIC
                m.d.comb += leds.eq(led_reg)

        return leds


    def add_ulpi_registers(self, m, platform, *, ulpi_bus, register_base):
        """ Adds a set of ULPI registers to the active design. """

        target_ulpi      = platform.request(ulpi_bus)

        ulpi_reg_window  = ULPIRegisterWindow()
        m.submodules  += ulpi_reg_window

        m.d.comb += [
            ulpi_reg_window.ulpi_data_in  .eq(target_ulpi.data.i),
            ulpi_reg_window.ulpi_dir      .eq(target_ulpi.dir.i),
            ulpi_reg_window.ulpi_next     .eq(target_ulpi.nxt.i),

            target_ulpi.clk.o    .eq(ClockSignal("usb")),
            target_ulpi.rst.o    .eq(ResetSignal("usb")),
            target_ulpi.stp.o    .eq(ulpi_reg_window.ulpi_stop),
            target_ulpi.data.o   .eq(ulpi_reg_window.ulpi_data_out),
            target_ulpi.data.oe  .eq(~target_ulpi.dir.i)
        ]

        register_address_change  = Signal()
        register_value_change    = Signal()

        # ULPI register address.
        registers = m.submodules.registers
        registers.add_register(register_base + 0,
            write_strobe=register_address_change,
            value_signal=ulpi_reg_window.address,
            size=6
        )
        m.submodules.clocking.stretch_sync_strobe_to_usb(m,
            strobe=register_address_change,
            output=ulpi_reg_window.read_request,
        )

        # ULPI register value.
        registers.add_sfr(register_base + 1,
            read=ulpi_reg_window.read_data,
            write_signal=ulpi_reg_window.write_data,
            write_strobe=register_value_change
        )
        m.submodules.clocking.stretch_sync_strobe_to_usb(m,
            strobe=register_value_change,
            output=ulpi_reg_window.write_request
        )
