# Review notes — OMEGAWARE FluxDrive HW Design v0.1

**From:** Dimmy's breadboard project (ESP32-S3 Super Mini + 74HCT125, Arduino Core 3.3.7)
**Re:** field-tested findings relevant to §3, §6 and especially the §8 bench gate

Context: we have a working-ish DF0 emulator on a breadboard — the Amiga polls it,
steps it, and attempts reads. We've spent several sessions inside exactly the RMT
layer your bench gate targets. Everything below is measured, not theorized.

---

## 1. RMT driver findings (directly affects §8)

### 1.1 The IDF driver silently fails under Arduino

If the firmware is Arduino-core based and you call the ESP-IDF v5 driver
(`rmt_new_tx_channel()` etc.) directly, the GPIO never gets attached to the RMT
peripheral — the Arduino perimanager owns the pin-to-bus bookkeeping and the raw
IDF call bypasses it. **No error, no output.** Cost us two firmware revisions.
Either go pure IDF, or use the Arduino HAL (`rmtInit`/`rmtWriteAsync`). Don't mix.

### 1.2 Hardware loop mode cannot hold a track

`rmtWriteLooping()` (and the underlying `loop_count=-1` transmit) requires the
**entire payload resident in RMT hardware memory**. On the S3 with 4 memory
blocks that is 192 symbols. A DD track is ~30–35k symbols (one per flux
transition). Error: `encoding artifacts can't exceed hw memory block for loop
transmission`. So "set and forget infinite loop" is off the table — your
1024-symbol ping-pong refill is the correct architecture, not a choice.

### 1.3 There is no abort for a running async transmit (Arduino layer)

`rmtWriteAsync()` cannot be cancelled. The only working stop is
`rmtDeinit()` + `rmtInit()` — a full channel teardown. Good news: on Core 3.3.7
this survived hundreds of stop/start cycles in our logs without the re-init
lockup reported on older cores. But budget ~the teardown cost per track change
if you use the Arduino layer. The IDF layer gives you `rmt_disable()`/
`rmt_enable()`, one more argument for pure IDF in your case.

### 1.4 No TX-done callback in the Arduino layer

Completion is poll-only (`rmtTransmitCompleted()` from `loop()`). With WiFi up,
loop latency is millisecond-scale and *variable* — so the track-wrap gap lands
wherever the scheduler feels like it. Your §6.3 "wrap in the gap" tip only holds
if the restart latency is bounded; with polling it isn't. IDF's
`on_trans_done` callback (IRAM, queue next buffer from the ISR) is the right
mechanism and fits your non-negotiable #3.

**Suggested §8 metric to add:** wrap-gap duration distribution (max, not just
mean) with radio flooding — that's the number that decides whether the gap
stays inside the track gap.

## 2. Timing data points (240 MHz S3, buffers in PSRAM)

| Operation | Measured |
|---|---|
| MFM-encode one DD track (11 sectors) | ~3.5 ms |
| Naive bit-loop convert to RMT symbols | ~12–17 ms |
| Total per track change (encode + convert) | ~15–20 ms |

Implication for §6.2's "pre-encode all 160 tracks (~50 ms, once)": at our
measured rate, encoding alone is 160 × 3.5 ms ≈ **560 ms**. Still perfectly fine
at insert time — just don't promise 50 ms, and note that bitcell→RMT-symbol
conversion adds more unless it happens in the refill path (which is where your
architecture puts it anyway — another point in its favor).

## 3. Amiga protocol — §6.3 confirmed the hard way

- **Motor latch is the #1 firmware trap.** We level-read `/MTR` for six firmware
  versions. The machine's rapid select/deselect polling made our state machine
  read "motor off" mid-load and kill the stream, over and over. Your one
  paragraph on the `/SEL`-edge latch is worth more than the rest of §6 combined.
- **Pin 2 / pin 34 swap is real.** We wired disk-change to pin 34 (PC habit).
  Your §2.1 warning table would have saved us weeks.
- Boot-time polling observed: brief select windows (low ms), step-to-clear-CHNG,
  repeated re-poll cycles. Whatever the emulator does, it must be listening and
  streamable *within* those windows — supports your pre-encode + latch design.

## 4. Hardware — endorsements from the school of hard knocks

- **LVC07A open-drain + LVC14A Schmitt: yes.** Our HCT125s run at 3.3 V VCC on
  the input side, which is out of spec for HCT (4.5–5.5 V) — it "works" with
  undefined thresholds. The push-pull output side plus DRVSEL-driven OE gating
  works but took multiple debug sessions (weak select line couldn't drive five
  OE pins; needed a buffer gate). Your §3 kills that entire failure class.
- **Power-on safe state (§3.2): also real.** We got it implicitly via OE gating;
  your pull-up trick achieves it with less hardware and no dependency on the
  select line's drive strength.

## 5. One suggestion: reserve a wired-link option

Consider reserving 2 spare GPIO (you have them, §5) routed to a UART header.
A wired display/GTi link at 2 Mbaud moves ~200 KB/s — an ADF in ~4.5 s — and
lets the emulator run **radio-silent permanently**. That doesn't just narrow
open item 8 (WiFi ISR stall tail); it deletes it. ESP-NOW stays as the wireless
option, but a two-pin header is free insurance, same spirit as the RP2350
footprint in §8.

---

*Summary: the design is sound and §6.3 is the crown jewel. The §8 bench gate
will pass on IDF with ISR-driven refill; it will produce misleading jitter if
built on the Arduino polling layer. Budget 0.5–1 s for insert-time pre-encode,
not 50 ms.*
