#!/usr/bin/env python3
#
# This file is part of Cynthion.
#
# Copyright (c) 2026 Great Scott Gadgets <info@greatscottgadgets.com>
# SPDX-License-Identifier: BSD-3-Clause

import unittest

from amaranth.sim import Simulator

from cynthion.gateware.facedancer.advertiser import PatternUartStreamer, UartTx


class TestUartTx(unittest.TestCase):
    def test_framing_for_a5(self):
        divisor = 4
        dut = UartTx(divisor=divisor)

        samples = []

        def driver():
            # Idle a few cycles.
            for _ in range(8):
                samples.append((yield dut.tx))
                yield

            # One-cycle valid pulse once ready.
            while not (yield dut.ready):
                samples.append((yield dut.tx))
                yield

            yield dut.data.eq(0xA5)
            yield dut.valid.eq(1)
            samples.append((yield dut.tx))
            yield
            yield dut.valid.eq(0)

            # Run long enough to capture full frame and return to idle.
            for _ in range(divisor * 12):
                samples.append((yield dut.tx))
                yield

        sim = Simulator(dut)
        sim.add_clock(1e-6)
        sim.add_sync_process(driver)
        sim.run()

        # Find first falling edge (start bit).
        start = None
        for i in range(1, len(samples)):
            if samples[i - 1] == 1 and samples[i] == 0:
                start = i
                break

        self.assertIsNotNone(start)

        expected_bits = [0]
        expected_bits.extend(((0xA5 >> bit) & 0x1) for bit in range(8))
        expected_bits.append(1)

        for bit_index, expected in enumerate(expected_bits):
            lo = start + bit_index * divisor
            hi = lo + divisor
            self.assertTrue(all(bit == expected for bit in samples[lo:hi]))


class TestPatternUartStreamer(unittest.TestCase):
    def test_pattern_stream_contains_expected_sequence(self):
        # 1 MHz clock, 500 kbaud -> 2 cycles/bit keeps simulation short.
        dut = PatternUartStreamer(clk_freq_hz=1_000_000, baud_rate=500_000, period_ms=0)
        divisor = 2

        samples = []

        def driver():
            yield dut.stop.eq(0)
            for _ in range(350):
                samples.append((yield dut.pad.o))
                yield

        sim = Simulator(dut)
        sim.add_clock(1e-6)
        sim.add_sync_process(driver)
        sim.run()

        decoded = _decode_uart_bytes(samples, divisor)

        self.assertGreaterEqual(len(decoded), 8)
        self.assertEqual(decoded[0:4], [0xC1, 0x14, 0x01, 0xA5])
        self.assertEqual(decoded[4:8], [0xC1, 0x14, 0x01, 0xA5])


def _decode_uart_bytes(samples, divisor):
    result = []
    i = 1

    while i + (10 * divisor) < len(samples):
        if samples[i - 1] == 1 and samples[i] == 0:
            # Candidate start bit.
            start_mid = i + (divisor // 2)
            if samples[start_mid] != 0:
                i += 1
                continue

            value = 0
            for bit in range(8):
                sample_index = i + divisor * (1 + bit) + (divisor // 2)
                value |= (samples[sample_index] & 1) << bit

            stop_mid = i + divisor * 9 + (divisor // 2)
            if samples[stop_mid] == 1:
                result.append(value)
                i += divisor * 10
                continue

        i += 1

    return result


if __name__ == "__main__":
    unittest.main()
