#!/usr/bin/env python3
#
# This file is part of Cynthion.
#
# Copyright (c) 2020-2024 Great Scott Gadgets <info@greatscottgadgets.com>
# SPDX-License-Identifier: BSD-3-Clause

REGISTER_ID = 1
REGISTER_LEDS = 2

# LED test modes. REGISTER_LED_MODE selects which source drives the LEDs;
# REGISTER_LEDS remains the pattern used by LED_MODE_STATIC.
REGISTER_LED_MODE = 3
REGISTER_LED_SPEED = 4

LED_MODE_STATIC   = 0   # drive REGISTER_LEDS directly (default, backwards compatible)
LED_MODE_CHASE    = 1   # single lit LED sweeping up
LED_MODE_BOUNCE   = 2   # single lit LED sweeping up and back down
LED_MODE_BLINK    = 3   # all LEDs blinking together
LED_MODE_COUNT_UP = 4   # 6-bit binary counter
LED_MODE_BAR      = 5   # bar filling up then emptying

LED_MODE_MAX = LED_MODE_BAR

REGISTER_TARGET_ADDR = 7
REGISTER_TARGET_VALUE = 8
REGISTER_TARGET_RXCMD = 9

REGISTER_AUX_ADDR = 10
REGISTER_AUX_VALUE = 11
REGISTER_AUX_RXCMD = 12

REGISTER_CONTROL_ADDR = 13
REGISTER_CONTROL_VALUE = 14
REGISTER_CONTROL_RXCMD = 15

REGISTER_RAM_REG_ADDR = 20
REGISTER_RAM_VALUE = 21
