# Investigation: Jog Wheel (Dial) Never Detects Counter-Clockwise Rotation

**Symptom (reported 2026-07-28):** in city mode, turning the dial clockwise correctly
selects the next city. Turning it counter-clockwise does not select the previous city —
it lands on some other, unrelated city instead.

**Root cause found: a wiring fault, not a software bug.** Encoder pin **A** was wired to
**GND**, and pin **C** (Common) was wired to **GPIO17**, the reverse of the correct
connections. This was found and corrected on-device on 2026-07-28; city indexing now
works correctly in both directions. This document records the checks performed to rule
out software causes and reach that conclusion, and the correct wiring for reference.

Encoder part: **Bourns PEC11R-4220K-S0024** — a bare 3-terminal incremental encoder (the
`S0024` option code has no integrated pushbutton switch, consistent with `dial.py`'s
device discovery finding no `EV_KEY` capability on the evdev device).

---

## 1. Ruling out the application layer

`journalctl --user-unit=radioglobe.service` was watched live while the user performed
controlled single clicks and confirmed multi-click spins in each direction. Across an
extended interactive session, **every** logged dial turn read `↪️ Dial turned: right
dir:1` — `left dir:-1` never appeared once, including for turns explicitly performed in
the opposite physical direction from an immediately preceding turn. Concrete example:
from `jog:60 Haddenham,GB`, a turn described as counter-clockwise produced `jog:61
Bicester,GB` (the *next* city, index 61) rather than `jog:59 Reading,GB` (the *previous*
city, index 59) — logged as `dir:1`.

`radioglobe/main.py`'s `next_city()`/`next_station()` index math
(`jog_idx = (jog_idx + direction) % len(items)`) was re-checked and confirmed correct and
symmetric in isolation — the bug was not in this arithmetic.

## 2. Ruling out `dial.py` (including the recent debounce-coalescing change)

To rule out a bug in the contact-bounce coalescing logic added in the previous fix (see
`KERNEL_ROTARY_ENCODER_INVESTIGATION.md` §9), raw kernel events were captured directly
from `/dev/input/event0`, bypassing `dial.py` entirely — using the deployed app's own
venv Python in a throwaway script (`evdev.InputDevice(...).read_loop()`, no `grab()`, so
it coexists with the running service's own reader):

- A continuous ~10-click spin in one direction: every event `REL_X value=+1` (two
  isolated `-1`s appeared only as bounce noise embedded within an otherwise-`+1` burst,
  not as a distinct click).
- A second continuous ~10-click spin, explicitly the reverse direction, confirmed
  verbally before and after: **also every event `REL_X value=+1`**, zero `-1` events.

This is conclusive that the raw kernel driver output was never negative for genuine
reverse rotation — the fault sits at or below the evdev layer, ruling out `dial.py` and
everything above it.

## 3. Confirming the overlay/driver was loaded correctly

```
$ gpioinfo | grep -E " 17:| 18:"
line  17:    "GPIO17"    input consumer="rotary@11"
line  18:    "GPIO18"    input consumer="rotary@11"
```

Both GPIO17 (`pin_a`) and GPIO18 (`pin_b`) were correctly claimed as inputs by the
`rotary_encoder` driver instance (`rotary@11`), confirming the
`dtoverlay=rotary-encoder,pin_a=17,pin_b=18,relative_axis=1` line in
`/boot/firmware/config.txt` had loaded as intended. This ruled out a gross overlay
misconfiguration or the wrong pins being bound.

## 4. Attempting a live GPIO-level trace

To try to pinpoint which physical line was at fault, the plan was to watch GPIO17 and
GPIO18 independently at the raw pin level with `gpiomon` (from `libgpiod`, already
installed) while turning the dial.

**This required more disruption than expected.** `radioglobe.service` holds no GPIO
claim itself — the claim belongs to the kernel `rotary_encoder` driver, loaded from
`/boot/firmware/config.txt` at **boot time**, before Linux even starts. This is a
different mechanism from the runtime `dtoverlay` configfs tool (`dtoverlay -l` reported
"No overlays loaded" even with the driver clearly active), so the overlay could not be
unloaded live — only by commenting out the `dtoverlay=` line and **rebooting**.

The overlay line was commented out and the device rebooted, freeing GPIO17/18
(`gpioinfo` then showed both lines with no consumer). `gpiomon -c gpiochip0 -b pull-up
-e both 17 18` was run while the user turned the dial several clicks each way.

**Result: inconclusive.** Both GPIO17 and GPIO18 showed heavy, indiscriminate
chattering — hundreds of edge transitions within a single millisecond, on both lines —
rather than the expected "one line dead, one line clean" pattern. This contradicted the
working hypothesis at the time (a single stuck/disconnected channel) and made the raw
trace too noisy to interpret confidently. A contributing factor considered: the
`dtoverlay=rotary-encoder` overlay has **no pull-up/pull-down parameter** at all (its
documented params are `pin_a`, `pin_b`, `relative_axis`, `linux_axis`, `rollover`,
`steps-per-period`, `steps`, `wakeup`, `encoding` — nothing for line bias), whereas the
pre-migration `dial.py` explicitly set `GPIO.PUD_UP` in software
(`radioglobe/dial.py`, before commit `252cd3c`). The PEC11R is a bare mechanical switch
encoder with no built-in pull-up resistors, so without an external pull-up or a reliable
default SoC pull state, the lines could plausibly float and pick up noise — `-b pull-up`
was passed to `gpiomon` for this trace, but did not produce a clean signal, so this
remains a secondary observation rather than the confirmed root cause.

The overlay line was restored and the device rebooted again to return the dial to normal
(if buggy) operation while further diagnosis continued.

## 5. Root cause: encoder pins A and C were swapped

Given the electrical trace was inconclusive, the encoder's physical wiring was inspected
directly against its datasheet pinout. **Pin A was connected to GND, and pin C
(Common) was connected to GPIO17** — the two were swapped relative to the correct
wiring.

This fully explains the symptom: with Common (the switch pole all contacts return
through) tied to GPIO17 instead of GND, and A tied to GND instead of the pole, the analog
switch topology `rotary_encoder`'s gray-code state machine expects is broken —
transitions on the true "B" channel no longer relate to a true "A" channel in the way
quadrature decoding requires, and a click can systematically resolve to the same reported
direction, or worse, essentially any credible-looking valid transition sequence,
regardless of which physical way the shaft actually turned. It also explains why the
earlier `gpiomon` trace looked like noise rather than clean quadrature: with Common on a
GPIO instead of ground, both "channel" GPIOs were toggling relative to a moving
reference rather than a stable ground return.

## 6. Correct wiring

| Encoder pin | Connects to |
|---|---|
| **A** | GPIO17 (BCM), physical header **pin 11** — `pin_a` in the `dtoverlay=rotary-encoder` line |
| **C** (Common) | Any **GND** pin on the 40-pin header (e.g. physical pin 9, 14, 20, ...) |
| **B** | GPIO18 (BCM), physical header **pin 12** — `pin_b` in the `dtoverlay=rotary-encoder` line |

**No pull-up resistors are currently fitted on A or B** — neither externally on the
encoder wiring, nor explicitly configured anywhere in software (the
`dtoverlay=rotary-encoder` overlay has no pull-up/pull-down parameter, unlike the
pre-migration `dial.py`, which set `GPIO.PUD_UP` explicitly; see §4). In practice this
appears to work: after the A/C swap was corrected, step counting and direction detection
have both been reliable, and the contact-bounce coalescing debounce added in
`KERNEL_ROTARY_ENCODER_INVESTIGATION.md` §9 (`DIAL_DEBOUNCE_S` in
`radioglobe/dial.py`) absorbs the noise this marginal setup produces. This is relying on
whatever default pull state GPIO17/18 happen to have rather than a guaranteed one,
though, so it's a latent fragility rather than a clean design.

**Future improvement:** add physical pull-up resistors (~10kΩ, A and B each to 3.3V) at
the encoder. This would give a clean, guaranteed-HIGH idle state on both channels
regardless of SoC default pull behaviour, reducing reliance on the software debounce
layer to paper over noise rather than needing to.

## 7. Fix and verification

The user corrected the physical wiring on-device (swapping the A and C connections back
to the table above). No code or configuration changes were needed — the overlay line in
`/boot/firmware/config.txt` and `radioglobe/dial.py` were already correct throughout this
investigation. Confirmed working: city-mode navigation now correctly steps to the
previous city on a counter-clockwise turn and the next city on a clockwise turn,
symmetrically, matching the expected behaviour described in
`KERNEL_ROTARY_ENCODER_INVESTIGATION.md` §6/§9.

---

## Related documents

- `docs/KERNEL_ROTARY_ENCODER_INVESTIGATION.md` — the original investigation into
  migrating the dial from `RPi.GPIO` polling to the kernel `rotary_encoder` driver (§6),
  and the later contact-bounce coalescing fix (§9). This document covers a distinct,
  later fault (wiring, not software) found after that migration.
- `ARCHITECTURE.md` §4.4 — `dial.py` module reference.
