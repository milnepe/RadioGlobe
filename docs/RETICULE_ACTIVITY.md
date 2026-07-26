# Activity Diagram: Moving the Reticule to a New Station

This diagram traces what happens when the user spins the globe to a new
reticule position, from the encoder's raw SPI reading through to a new
station playing. It assumes the origin has already been calibrated
(`zero()` has been called), so `encoders.get_readings()` returns an
absolute `(lat, lon)` position rather than a raw, uncalibrated one.

It complements [ARCHITECTURE.md](../ARCHITECTURE.md) — see
[§5 Flow A](../ARCHITECTURE.md#5-key-data-flows) for the prose version of
the happy path. The empty-stations guard shown below was originally
[§11 Improvement A](../ARCHITECTURE.md#11-suggested-improvements) (an
unguarded `IndexError`); it shipped in `v0.5.1`.

## Legend

- `[ box ]` — an action: a function call or state change
- `<< box >>` — a decision point
- `|` / `v` — control flows downward along the main spine
- boxes to the right of the spine are the **no** branch of the decision
  directly above them; the **yes** branch continues straight down
- `LOOP-A` — a jump target; branches that say "back to LOOP-A" return
  control to that point rather than falling off the page

## Diagram

```
Assumption: origin has already been calibrated -- zero() has been called,
so encoders.get_readings() returns the absolute (lat, lon) position.

                              ( start )
                                 |
                                 v
      +----------------------------------------------------+
      |  User spins the globe to a new reticule position   |
      +----------------------------------------------------+
                                 |
                                 v
      +==== LOOP-A =======================================+
                                 |
                                 v
      +----------------------------------------------------+
      |           run_encoder() polls SPI bus 0            |
      |        (background task, runs every 50 ms)         |
      +----------------------------------------------------+
                                 |
                                 v
      +----------------------------------------------------+
      |    check_parity() validates the raw SPI reading    |
      +----------------------------------------------------+
                                 |
                                 v
      +----------------------------------------------------+
      |                  << parity OK? >>                  |
      +----------------------------------------------------+
                                 |    no
                                 |    +----------------------------------+
                                 |    |       Discard the reading.       |
                                 |    +----------------------------------+
                                 |    (loops back to LOOP-A on the
                                 |     next 50 ms SPI poll)
                                 v   (yes)
      +----------------------------------------------------+
      |       Update self.latitude / self.longitude        |
      |        set encoders.updated (asyncio.Event)        |
      +----------------------------------------------------+
                                 |
                                 v
      +----------------------------------------------------+
      |     _encoder_loop() wakes on encoders.updated;     |
      |                  clears the event                  |
      +----------------------------------------------------+
                                 |
                                 v
      +----------------------------------------------------+
      |          coords = encoders.get_readings()          |
      +----------------------------------------------------+
                                 |
                                 v
      +----------------------------------------------------+
      |         cities = find_cities_near(coords,          |
      |         look_around_offsets, cities_index)         |
      +----------------------------------------------------+
                                 |
                                 v
      +----------------------------------------------------+
      |             cities found AND encoders              |
      |                not already latched?                |
      +----------------------------------------------------+
                                 |    no
                                 |    +----------------------------------+
                                 |    |   No city near this position.    |
                                 |    |     Encoders stay unlatched;     |
                                 |    |      no station is played.       |
                                 |    +----------------------------------+
                                 |    ----> back to LOOP-A
                                 v   (yes)
      +----------------------------------------------------+
      |   encoders.latch(*coords, stickiness=STICKINESS)   |
      |           freezes the reticule position            |
      +----------------------------------------------------+
                                 |
                                 v
      +----------------------------------------------------+
      |         city = cities[0]  (closest match)          |
      |        jog_idx = 0   |   LED flashes green         |
      +----------------------------------------------------+
                                 |
                                 v
      +----------------------------------------------------+
      |          stations = get_stations_by_city(          |
      |                 stations_info, city)               |
      +----------------------------------------------------+
                                 |
                                 v
      +----------------------------------------------------+
      |           << stations list non-empty? >>           |
      +----------------------------------------------------+
                                 |    no
                                 |    +----------------------------------+
                                 |    |          Log a warning.          |
                                 |    |      encoders.reset_latch()      |
                                 |    |       (releases the frozen       |
                                 |    |     position so the reticule     |
                                 |    |         can search again)        |
                                 |    +----------------------------------+
                                 |    ----> back to LOOP-A
                                 v   (yes)
      +----------------------------------------------------+
      |               station = stations[0]                |
      +----------------------------------------------------+
                                 |
                                 v
      +----------------------------------------------------+
      |          display.update(coords, city, 0,           |
      |                 station[0], False)                 |
      +----------------------------------------------------+
                                 |
                                 v
      +----------------------------------------------------+
      |          audio_player.play(city, station)          |
      +----------------------------------------------------+
                                 |
                                 v
      +----------------------------------------------------+
      |         _start_monitor_stream(station[1])          |
      |     (watches for stream failure -- see Flow A      |
      |                in ARCHITECTURE.md)                 |
      +----------------------------------------------------+
                                 |
                                 v
                    (( end: new station is playing ))
```

## What happens if a station isn't found at the new location?

There are two distinct cases, and the codebase handles them very
differently:

**1. No city is found near the new position (the common case).**
`find_cities_near()` returns an empty list. Because the decision
`cities found AND encoders not already latched?` is now false, nothing
is latched, no display update happens, and no station starts playing.
`_encoder_loop()` simply loops back to `LOOP-A` and keeps waiting on
`encoders.updated` — the app stays exactly where it was (still
unlatched, still showing whatever it showed before, or the calibrate
screen if this is the first move since boot). As soon as the reticule
drifts over a point close enough to a known city, the next `updated`
event picks it up and plays it. This is the expected, everyday
behaviour of "spinning between cities" — nothing is ever a hard error.

**2. A city is found, but its station list is empty.** This can only
happen with malformed data — a city key present in `stations.json` with
no (or an empty) `"urls"` entry, e.g. from a partial database update.
As of `v0.5.1`, this is guarded: right after the latch,
`_encoder_loop()` checks `if not self.state.stations`, logs a warning,
calls `encoders.reset_latch()` to release the frozen position, and
loops back to `LOOP-A` instead of indexing into the empty list — no
crash, no restart needed. The same guard was added to the identical
call site in `_dial_loop()` (after `next_city()`), where it instead
skips the display/playback update and leaves the previous station
playing. This closed what was originally
[ARCHITECTURE.md §11, Improvement A](../ARCHITECTURE.md#11-suggested-improvements)
(an unguarded `IndexError`), verified on real hardware before merging —
see `radioglobe/main.py`'s `_encoder_loop()`/`_dial_loop()`.
