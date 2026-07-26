# Investigation: Can the Linux Kernel Rotary-Encoder Driver Improve Reticule/Globe Responsiveness?

**Question asked:** Could `drivers/input/misc/rotary_encoder.c` — the stock Linux kernel
GPIO rotary-encoder driver — be used to read the reticule/globe position encoders, in
order to make the globe-to-station lookup feel more responsive?

**Short answer: no, not directly.** The kernel's `rotary_encoder` driver decodes a
GPIO A/B quadrature signal. The reticule/globe position sensors are SPI-read **absolute**
encoders (confirmed part: Bourns EMS22A50-D28-LT6), not GPIO quadrature — a different
device class entirely, and one with no interrupt or data-ready output at all (see §3).
The driver is a clean fit for a *different* encoder already in this codebase (the
station/city dial), but not for the one the responsiveness question is actually about.
The real fix for reticule/globe responsiveness doesn't need a kernel driver — it's a
one-line change to a `asyncio.sleep()` call, discussed in
[§5](#5-what-would-actually-help-reticuleglobe-responsiveness).

---

## 1. What's actually being read today

RadioGlobe has **two** rotary encoders and they are not the same kind of device:

| | Reticule/globe position ("globe encoders") | Station/city dial ("jog wheel") |
|---|---|---|
| File | `radioglobe/positional_encoders.py` | `radioglobe/dial.py` |
| Part | Bourns EMS22A50-D28-LT6 (confirmed, see §2) | Unidentified quadrature module |
| Bus | SPI bus 0, device 0 (lat) and device 1 (lon) | GPIO, BCM pins 17 (clock) / 18 (direction) |
| Encoder type | **Absolute** — each read returns a full 10-bit position (0–1023), no history needed | **Incremental** — each pulse is a relative step, direction read from a second pin |
| How it's read today | Python `spidev.SpiDev()`, polled every 200ms | `RPi.GPIO.wait_for_edge()` in a thread, per-edge |
| Kernel involvement today | None — plain `spidev` char device, userspace does everything | None — `RPi.GPIO`/`rpi-lgpio` userspace edge polling |

### 1.1 Reticule/globe encoders (`positional_encoders.py`)

```python
# radioglobe/positional_encoders.py:55-72
def read_spi(self):
    BUS = 0
    readings = []
    for device in [0, 1]:
        self.spi.open(BUS, device)
        self.spi.max_speed_hz = 5000
        self.spi.mode = 1
        reading = self.spi.readbytes(2)
        self.spi.close()
        raw_reading = reading[0] << 8 | reading[1]
        if self.check_parity(raw_reading):
            readings.append(raw_reading >> 6)
        else:
            return None
    return readings
```

The polling loop:

```python
# radioglobe/positional_encoders.py:74-98
async def run_encoder(self):
    while self._task:
        readings = self.read_spi()
        if readings:
            ...
            self.updated.set()   # or unlatch, see ARCHITECTURE.md
        await asyncio.sleep(0.2)   # <-- fixed 200ms poll interval
```

### 1.2 Station/city dial (`dial.py`)

```python
# radioglobe/dial.py (paraphrased)
GPIO.setup([PIN_DIAL_CLOCK, PIN_DIAL_DIR], GPIO.IN, pull_up_down=GPIO.PUD_UP)
...
async def run_encoder(self):
    while ...:
        await asyncio.to_thread(GPIO.wait_for_edge, PIN_DIAL_CLOCK, GPIO.FALLING)
        direction = GPIO.input(PIN_DIAL_DIR) * -1
        self.queue.put_nowait(direction)
        await asyncio.sleep(0.3)   # 300ms software debounce
```

This is a standard two-phase quadrature encoder (clock/direction is just this board's
naming for what's usually called A/B or CLK/DT on breakout modules) — falling edges on
one channel, sampling the level of the other to get direction. This is architecturally
exactly what the kernel's `rotary_encoder` driver and the `rotary-encoder` device-tree
overlay are built for (§4).

---

## 2. The reticule/globe part, confirmed: Bourns EMS22A50-D28-LT6

Datasheet: `bourns.com/docs/Product-Datasheets/EMS22A.pdf` (EMS22A family, non-contacting
magnetic absolute encoder, 1024-position/10-bit resolution — matches
`ENCODER_RESOLUTION = 1024` in `radio_config.py` exactly).

**Pin configuration (Absolute output variant, per datasheet):**

| Pin | Name | Function |
|---|---|---|
| 1 | DI | Digital Input — daisy-chain input from a previous device; grounded in a single-sensor configuration |
| 2 | CLK | Clock (host-driven) |
| 3 | — | GND |
| 4 | DO | Digital Output (data out) |
| 5 | — | VCC (5 V or 3.3 V depending on part variant) |
| 6 | CS | Chip Select (host-driven) |

**That's the entire interface: DI, CLK, GND, DO, VCC, CS.** RadioGlobe wires the two
encoders (lat, lon) as independent SPI devices on chip-selects 0 and 1 rather than
daisy-chaining them through DI/DO on a shared CS — consistent with `spidev.open(0, 0)` /
`spidev.open(0, 1)` in `read_spi()`.

**Serial frame, confirmed against the code:** the datasheet specifies a 16-clock read
frame:

```
D9 D8 D7 D6 D5 D4 D3 D2 D1 D0 | S1 S2 S3 S4 S5 | P1
└──── 10-bit position ────┘   └─ status bits ─┘  parity
```

| Bits | Meaning |
|---|---|
| D9:D0 | Absolute angular position (10-bit) |
| S1 | End of offset-compensation algorithm |
| S2 | CORDIC overflow (internal computation error) |
| S3 | Linearity alarm |
| S4 | Magnetic magnitude increasing (out of range warning) |
| S5 | Magnetic magnitude decreasing (out of range warning) |
| P1 | Even parity over bits 1–15 |

This lines up exactly with `positional_encoders.py`: `raw_reading >> 6` takes the top 10
bits (D9:D0), and `check_parity()` validates P1 against an XOR of the other 15 bits. One
side note, not part of the responsiveness question but worth flagging separately: the S1–S5
status bits (offset-compensation state, CORDIC error, linearity alarm, magnetic-field
strength warnings) are currently read off the wire and then discarded — they're shifted
away by `>> 6` — so any early warning of a degrading magnetic read (e.g. a shaft/magnet
gap issue developing over time) is silently unused today.

**Timing, per the datasheet's waveform diagrams:** minimum half clock period (`T_CLK/2`)
is 500ns, i.e. **≈1 MHz maximum clock frequency**. RadioGlobe currently drives this at
`max_speed_hz=5000` (5 kHz) — roughly **200x below** what the part supports. This is
concrete headroom for §5.3.

---

## 3. Does it have any interrupt/data-ready output? No.

**Confirmed from the datasheet pinout: no.** The EMS22A is a purely passive SSI-style
slave device with exactly six pins (DI, CLK, GND, DO, VCC, CS) and no additional signal
line of any kind. There is no data-ready pin, no index/marker pulse, no interrupt output,
and no way for the encoder to signal the host asynchronously. Every single position
reading must be actively initiated by the host toggling CS and clocking CLK — the part
cannot notify the Raspberry Pi of anything on its own.

This rules out an entire category of improvement: there is no hardware signal to attach a
GPIO interrupt to, so an event-driven "wake on position change" design is not achievable
with this part regardless of software or kernel-driver approach. Polling — at some
interval, fast or slow, in userspace or in a kernel driver — is the only option this
hardware supports. That reframes the responsiveness question entirely around *how fast
and how efficiently the host can poll*, not around finding an interrupt to attach to.

---

## 4. What the kernel rotary-encoder driver actually is

Verified directly on a RadioGlobe device over SSH (read-only checks, no service impact):

```
$ uname -a
Linux radioglobe 6.12.75+rpt-rpi-v8 #1 SMP PREEMPT Debian 1:6.12.75-1+rpt1~bookworm ... aarch64

$ cat /etc/os-release
PRETTY_NAME="Debian GNU/Linux 12 (bookworm)"

$ ls /lib/modules/$(uname -r)/kernel/drivers/input/misc/ | grep rotary
rotary_encoder.ko.xz

$ ls /boot/firmware/overlays/ | grep rotary
rotary-encoder.dtbo

$ sudo dtoverlay -h rotary-encoder
Name:   rotary-encoder
Info:   Overlay for GPIO connected rotary encoder.
Usage:  dtoverlay=rotary-encoder,<param>=<val>
Params: pin_a                   GPIO connected to rotary encoder channel A (default 4)
        pin_b                   GPIO connected to rotary encoder channel B (default 17)
        relative_axis           register a relative axis rather than an absolute one
        linux_axis              input subsystem axis to map to (default 0 / ABS_X / REL_X)
        rollover                automatic rollover for absolute axis
        steps-per-period        1 (full), 2 (half), 4 (quarter) period mode
        steps                   steps per full turnaround (absolute axis only, default 24)
        wakeup                  can wake the system
        encoding                "gray" (default) or "binary"
```

Both the module and the device-tree overlay ship out of the box on Raspberry Pi OS
Bookworm — nothing to build or install. The driver registers GPIO IRQs on the two named
pins, runs a small gray/binary-code state machine in an interrupt handler, and exposes the
result as a standard Linux input device (`/dev/input/eventN`) emitting `EV_REL` or
`EV_ABS` events — readable from userspace with `python-evdev`, no polling required.

This is a good match for **`dial.py`** (§5 discusses this), and a non-match for the
reticule/globe SPI encoders, because the overlay's only inputs are two GPIO pin numbers —
there is nowhere to plug in a SPI bus/device pair, and the driver's internal model (count
transitions between two binary GPIO lines) doesn't map onto "shift N bits out of an SSI
slave over SPI."

---

## 5. Why the kernel driver can't be used for the reticule/globe encoders

1. **Wrong bus.** The overlay and driver are GPIO-only (`pin_a`, `pin_b`). The EMS22A50
   lives on SPI (CLK/DO/CS/DI, §2) — there's no GPIO A/B pair to point the overlay at.
2. **Wrong encoder model.** The driver's entire job is decoding relative quadrature
   transitions into a running count. The EMS22A50 already emits an absolute 10-bit
   position per read; there's nothing incremental to decode, and no state machine needed.
3. **No interrupt to hook into anyway.** Even ignoring the bus/protocol mismatch, §3
   established the part has no output that could trigger a GPIO IRQ in the first place.
4. **No existing in-kernel driver for this SPI protocol.** The Linux IIO subsystem has
   drivers for various absolute encoder/resolver chips, but there's no generic SSI/parity
   driver bundled in mainline or the Raspberry Pi kernel fork that a stock device-tree
   overlay could bind to, the way `rotary-encoder` works for GPIO parts. Kernel-level
   reads of this specific part would mean **writing** a driver (§6.5), not enabling one.

---

## 6. Where the kernel driver genuinely would help: the dial

Not the original question, but worth recording since it's directly relevant and low-risk.
`dial.py`'s current approach — `GPIO.wait_for_edge()` blocked on a thread-pool thread via
`asyncio.to_thread`, plus a 300ms software debounce sleep — could be replaced with:

```
# /boot/firmware/config.txt
dtoverlay=rotary-encoder,pin_a=17,pin_b=18,relative_axis=1
```

...then in Python, register the resulting `/dev/input/eventN` fd with the asyncio event
loop (`loop.add_reader(fd, callback)`) and read `evdev` events directly — no thread pool,
no `wait_for_edge`, debounce handled by the kernel's IRQ-driven state machine instead of a
fixed sleep. This is a genuine architectural improvement to `dial.py` (removes a blocking
call and a thread hop from the hot path), but it improves *dial responsiveness*, not
*reticule/globe responsiveness* — they are unrelated code paths (`_dial_loop()` vs.
`_encoder_loop()` in `main.py`). Flagging it here so it isn't confused with the actual ask.

---

## 7. What would actually help reticule/globe responsiveness

Ordered cheapest/lowest-risk to most expensive. Since there's no interrupt to exploit
(§3), every option below is still fundamentally "poll faster/smarter" — the question is
where that polling happens and how efficiently.

### 7.1 Profile before changing anything

There's no documented responsiveness complaint in the repo — `RETICULE_ACTIVITY.md` and
`ARCHITECTURE.md` describe the 200ms poll as normal behaviour, not a bug. Before spending
effort, measure the actual reticule-move-to-city-found latency (e.g. timestamp at
`run_encoder()`'s `self.updated.set()` vs. the moment the position last changed physically)
to confirm the 200ms poll is the dominant term, rather than VLC stream startup or network
jitter, which are much larger (VLC's `--network-caching=2000` alone is a 2-second buffer,
`audio_async.py`).

### 7.2 Shrink the poll interval (cheapest, highest-leverage change)

```python
# positional_encoders.py:98
await asyncio.sleep(0.2)   # → try 0.02–0.05
```

At the current 5000 Hz SPI clock, a 16-bit transfer takes ~3.2ms; two devices plus
`spidev` open/close overhead is still well under 10ms per cycle — comfortably fits inside
a 20-50ms loop with room to spare. This alone could cut worst-case detection latency by
4–10x with no kernel involvement, no new dependencies, and no new failure modes. Measure
against CPU usage (the loop now runs 4–10x more often) and against false-positive
re-latching (check whether `STICKINESS`/jitter suppression, added in commits
`71acccc`/`99ae389`, still holds at a tighter poll rate).

### 7.3 Raise the SPI clock speed

The datasheet's minimum half-clock-period spec (`T_CLK/2` ≥ 500ns) puts the EMS22A50's
maximum serial clock at roughly **1 MHz** — RadioGlobe currently uses **5000 Hz**, about
200x lower. Raising `max_speed_hz` in `read_spi()` shrinks per-read transfer time well
below a millisecond, which matters most once §7.2 has tightened the poll interval enough
that transfer time is a non-trivial fraction of the cycle. Worth testing incrementally
(e.g. 50kHz → 200kHz → 1MHz) rather than jumping straight to the datasheet maximum, to
check for signal integrity issues on the actual wiring/cable length used on the physical
board.

### 7.4 Event-driven reads: not available on this hardware

Ruled out definitively in §3 — the EMS22A50 has no data-ready, interrupt, or index output
pin. There is no wiring change or board rework that unlocks this; it would require
swapping the sensor for a different part entirely, which is a far larger undertaking than
this investigation's scope and not recommended given §7.2/§7.3 already close most of the
gap.

### 7.5 Custom kernel driver (last resort, high effort)

Only worth doing if §7.1's profiling shows that *userspace/Python scheduling jitter*
specifically — not the poll interval choice itself — is the bottleneck (e.g. the asyncio
loop is measurably delayed getting back to the encoder task because of GC pauses, other
tasks, or Python's GIL). Given there's no interrupt to drive it (§3), this would be a
**timer-driven** kernel poller, not an IRQ-driven one — a materially smaller latency win
than a true interrupt-driven driver would offer, since it only removes Python/asyncio
scheduling variance, not the fundamental need to poll. If pursued, it would look like:

**OS-level changes:**
- A device-tree overlay binding the EMS22A50 to `spi0.0`/`spi0.1` with a custom compatible
  string (replacing/coexisting with the generic `spidev` binding currently used).
- A kernel module (out-of-tree, packaged with **DKMS** so it survives `apt full-upgrade`
  kernel bumps — Raspberry Pi OS updates its kernel package independently of the rest of
  the system) implementing an `spi_driver` with a `probe()` that runs a periodic
  `spi_sync()` from an `hrtimer`/kthread and pushes results through the **Linux input
  subsystem** (`input_report_abs()` + `input_sync()`) so userspace still just reads
  `/dev/input/eventN`, or via the **IIO subsystem** (more idiomatic for absolute position
  sensors, but a less direct fit for this app's existing event/asyncio model).
- Porting `check_parity()` (currently ~10 lines of Python) into the kernel module in C,
  and optionally surfacing the S1–S5 status bits (§2) that are discarded today — a
  legitimate secondary benefit of writing a real driver, since the Linux input/IIO
  subsystems have room for auxiliary status/error reporting that the current Python code
  simply throws away.
- Testing/debugging shifts from Python exceptions and `pytest` to kernel oops/panics,
  `dmesg`, and needing a serial console or SSH-recoverable system for iteration — a much
  slower and riskier development loop on hardware that's also driving a physical globe.

**Code-level changes (Python side):**
- Replace `spidev.SpiDev()` calls in `positional_encoders.py` with either a `python-evdev`
  read loop (input-subsystem route) or a small `sysfs`/`libiio` read wrapper (IIO route).
- The offset/latch logic and the `asyncio.Event`-based wakeup in `run_encoder()` would
  still be needed in Python — the kernel driver only replaces the raw read, not the app's
  latch/stickiness semantics.

**Trade-off:** this buys timer-driven reads free of Python/asyncio scheduling jitter, at
the cost of a real kernel-maintenance burden (rebuilds on every kernel update unless DKMS
is set up correctly, a much harder debugging story, and a single-purpose driver that only
this project's maintainer(s) can support) — for a latency win that's smaller than it might
first appear, since there's still no interrupt behind it. Given that §7.2 alone is
expected to close most of the 200ms gap for free, this option is very unlikely to be worth
it unless profiling in §7.1 proves otherwise.

---

## 8. Recommendation

1. **Do not pursue the stock kernel `rotary_encoder` driver for the reticule/globe
   encoders** — it's the wrong device class (GPIO quadrature vs. SPI absolute, confirmed
   Bourns EMS22A50-D28-LT6) and the part has no interrupt/data-ready signal to hook into
   regardless (§3).
2. **Do** consider it opportunistically for `dial.py` (§6) — separate, low-risk, already
   works out of the box on this kernel/OS combination.
3. For the actual responsiveness goal, **start with §7.2** (shrink `asyncio.sleep(0.2)`
   in `positional_encoders.py:98`) and **§7.3** (raise `max_speed_hz` from 5000 toward the
   datasheet's ~1 MHz ceiling) — both near-zero effort, no new dependencies, and together
   they directly target the only two latency terms this hardware actually allows anyone
   to control. Only escalate to §7.5 if measurement shows these insufficient.

---

## Appendix: What was verified vs. inferred

| Claim | Status |
|---|---|
| Kernel version 6.12.75+rpt-rpi-v8, Debian 12 Bookworm | Verified live via SSH (`uname -a`, `/etc/os-release`) |
| `rotary_encoder.ko.xz` present in kernel modules dir | Verified live via SSH |
| `rotary-encoder.dtbo` present, overlay parameters as listed | Verified live via SSH (`dtoverlay -h`) |
| SPI/I2C kernel modules loaded (`spidev`, `spi_bcm2835`, `i2c_dev`, etc.) | Verified live via SSH |
| Reticule/globe part is Bourns EMS22A50-D28-LT6 | Confirmed by user; cross-checked against Bourns EMS22A datasheet |
| Pinout: DI, CLK, GND, DO, VCC, CS — no interrupt/data-ready/index pin | Verified against datasheet pin configuration table |
| 16-bit frame: D9:D0 position, S1–S5 status, P1 parity | Verified against datasheet waveform/data-content table; matches `positional_encoders.py`'s `>> 6` and `check_parity()` exactly |
| Max serial clock ≈1 MHz (`T_CLK/2` ≥ 500 ns) vs. 5000 Hz used today | Verified against datasheet timing diagram |
| 200ms poll interval, dial 300ms debounce, button 50ms debounce | Verified from source (`positional_encoders.py`, `dial.py`, `buttons.py`) |
| Any documented responsiveness complaint from users | **None found** in README, ARCHITECTURE.md, RETICULE_ACTIVITY.md, or commit history |
