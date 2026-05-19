# Hardware

**Cynthion** — Great Scott Gadgets USB test instrument
- USB VID:PID: 1d50:615b (all gateware modes: analyzer, facedancer)
- Apollo bootloader: 1d50:60e6 (shown when no gateware is loaded)
- The VID:PID alone does not tell you which gateware is running —
  check the USB interface subclass: 0x10 = analyzer, 0x20 = moondancer/facedancer

**UTi261M** — UNI-T thermal imaging camera, controlled by UNIT Android app
- USB VID:PID: 0bda:5830 (Realtek UVC chip)
- Presents as USB Video Class (UVC) device
- Connects to Cynthion TARGET-C port for proxy

# Environment

## Python venv

Uses Python 3.11. Install from **PyPI** (not local source) so the pre-built
gateware bitstreams ship with the package.

```
./scripts/setup-venv.sh
```

Logs to `tmp/setup-venv.log`.

Why PyPI not local source: the local repo only contains `analyzer.bit` in
`cynthion/python/build/`. The `facedancer.bit` and `moondancer.bin` assets
are built separately and distributed via PyPI. Installing from local source
gives you only `apollo.bin` and the proxy cannot load facedancer gateware.

When making code changes to the cynthion Python package, reinstall local
source on top after setup:

```
venv/bin/pip install cynthion/python
```

## Device states and transitions

```
Power on (gateware flashed)  →  1d50:615b  analyzer or facedancer mode
Power on (no gateware)       →  1d50:60e6  Apollo bootloader

cynthion run facedancer      →  loads facedancer.bit + moondancer.bin via Apollo
                                device reappears at 1d50:615b with subclass 0x20

cynthion update              →  flashes analyzer.bit to config flash
                                device comes back as analyzer (subclass 0x10) after power cycle
```

After a proxy crash the Cynthion is left unresponsive at the USB command level
(`cynthion.Cynthion()` raises `USBErrorTimeout` or `DeviceNotFoundError`) but still
visible to `lsusb`. Power cycle required to recover (issue #7).

## udev / permissions

udev rule: `/etc/udev/rules.d/54-cynthion.rules`
User `dan` gets rw access via uaccess ACL — no plugdev group required.
