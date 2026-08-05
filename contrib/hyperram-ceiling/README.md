# HyperRAM clock ceiling

Finds the clock the HyperRAM stops verifying at, for both PHYs, on the same
board and the same harness, so the only variable is the PHY and the device
clock.

```
./ceiling.py --build   # bitstreams only; the board is not involved
./ceiling.py --run     # board only, uses what is already built
./ceiling.py           # both
```

Needs `cynthion`, `luna` and `apollo_fpga` importable, and yosys, nextpnr-ecp5
and ecppack on `PATH`. Bitstreams and `results.json` land in `build/`.

## The x-axis is device CK, not `sync`

`HyperRAMPHY` gears 2:1 and clocks the part at `sync`. `HyperRAMDQSPHY` gears
4:1 and clocks it at **twice** `sync`. A sweep indexed by `sync` would compare a
part running at 120 MHz against one running at 240 and call that a PHY
comparison. Every rung here is a CK, and each PHY is built for it at the `sync`
it needs.

That difference is the interesting one. `HyperRAMPHY` puts the *fabric* at CK,
so raising CK raises what the whole design must close at; `HyperRAMDQSPHY` puts
the fabric at CK/2.

## What makes a rung's verdict mean something

Every recorded trap on this interface produced a plausible wrong answer rather
than a failure, so "it passed" needs support:

* **A negative control, every rung.** Reads are checked against the complement
  of what was written, which the part cannot return, so a working comparator
  must report every word wrong. Without it, zero errors is equally consistent
  with a comparator that never fires.
* **BURSTDET**, latched from `DQSBUFM`. With fixed latency set in CR0 a read can
  come back clean because the count landed right rather than because the strobe
  was found. A DQS rung passing with BURSTDET clear has not demonstrated DQS.
* **An address-derived pattern.** A controller that stopped advancing would
  return one word forever, and a constant fill would score that as perfect.
* **Every mismatch counted, and the first one kept** with its index, what
  arrived and what was due -- a half-word slip, a stuck lane and noise are told
  apart by *how* the value is wrong.
* **Die temperature** before and after, so a rung that failed while the part was
  hotter than the rung below is not read as a clock limit.
* **The bitstream states the clock it was built for**, and the host checks it
  against its own idea before measuring.

`BURST_WORDS` is 128 because CR1[1:0] selects a 4 us tCSM -- the longest CS# may
stay low before distributed refresh is starved. A longer burst is not slow, it
is illegal, and it fails by forgetting later rather than by returning anything
wrong at the time.

## Prerequisites in luna

`HyperRAMDQSPHY` has to elaborate on Amaranth 0.5, and `readclksel` has to be a
constructor parameter for the phase sweep. Both are separate changes.

## Known gap

`HyperRAMDQSPHY` keeps `DDRDLLA`'s LOCK and the end of its PAUSE sequence
internal, so the two status bits meant to carry them read as constant 1. The
whole read path's delay codes are invalid until that DLL locks, and nothing
above the PHY can tell -- a design reporting a clean read with the DLL unlocked
has measured nothing. Worth exposing.
