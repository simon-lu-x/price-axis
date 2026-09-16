# Price axis specification

Version `1.0.0`.

Given the range of a price series, produce the axis bounds, the tick step, the tick
values, and the number of decimal places used to render them.

This document is normative. Two implementations that follow it must produce identical
output for identical input; `vectors.json` is the shared conformance fixture that proves
it.

## Inputs

| Name | Default | Meaning |
|---|---|---|
| `dataMin`, `dataMax` | — | Observed range of the series. `dataMax >= dataMin` |
| `maxTicks` | `8` | Upper bound on the number of ticks. Must be `>= 3`, see R5 |
| `padding` | `0.05` | Headroom above and below the series, as a fraction of its span |
| `minDecimals` | `0` | Precision floor. Labels never render with fewer decimals than this |
| `maxDecimals` | `6` | Precision ceiling. No label may exceed this |

Any non-finite input, `dataMax < dataMin`, `maxTicks < 3`, `padding < 0`, or
`minDecimals > maxDecimals` is an error. Implementations must reject, not repair.

## Rules

### R1 — Flat market

The market is flat when `dataMax - dataMin <= |dataMax| * 1e-12`. A flat series has no
span to scale to, so one is synthesised and padding is not applied:

- if the value is exactly `0`, the working range is `[-1, +1]`
- otherwise it is `value * (1 -/+ 0.001)`

Without this rule a flat series produces a zero-height axis and the chart renders empty.

### R2 — Padding

For a non-flat series the working range is `[dataMin - span*padding, dataMax + span*padding]`,
where `span = dataMax - dataMin`. Padding is symmetric.

### R3 — Nice step

Ticks sit at integer multiples of a step of the form `m * 10^n`, where `m` is `1`, `2` or
`5`. `niceStep(raw)` is the smallest such value that is `>= raw`. The first candidate
step is `niceStep(workingSpan / (maxTicks - 1))`: the smallest step that could fit inside
the tick budget, so the resulting axis is the tightest one the constraints allow.

`10^n` must be obtained by parsing the decimal literal `1e<n>`, not from a library `pow`.
Parsing is correctly rounded on every platform; `pow` is not required to be, so two
implementations that both look correct can return doubles differing in the last bit and
then fail the conformance fixture. This clause was added after the JavaScript
implementation exposed it; the first draft of this document did not say how to compute a
power of ten at all.

### R4 — Snapping and coverage

`axisMin = floor(workingMin / step) * step`, `axisMax = ceil(workingMax / step) * step`,
and `count = (axisMax - axisMin) / step + 1`.

Floating-point division can land a hair on the wrong side of an integer, so after
snapping the bounds are widened by whole steps until `axisMin <= dataMin` and
`axisMax >= dataMax`. Coverage of the real data is a hard post-condition (I2); the
snapped value is only a starting point.

### R5 — Step widening

A candidate step is rejected when either:

- `count > maxTicks`, or
- `step < 10^-maxDecimals`, so its ticks could not be rendered distinctly

On rejection the step advances to the next nice value (`1 -> 2 -> 5 -> 10`) and R4 runs
again. The loop terminates because each iteration multiplies the step by at least 2 while the
working span is fixed.

It terminates at three ticks, not two. R4 snaps both bounds outward, so unless the
series happens to fall between two adjacent multiples of the step, widening drives the
count down to three and no further: one multiple below the series, one above, and the
one between them. A budget of two is therefore unsatisfiable for most inputs, which is
why `maxTicks >= 3` is a precondition rather than a best effort. This was found by the
randomised sweep, not by reasoning, after an earlier draft accepted `maxTicks = 2` and
then failed to converge on a flat series near 1e8.

The second condition is the reason the loop exists at all. A step of `2e-8` under
`maxDecimals = 6` would render several ticks as the same string; widening to `1e-6` is
the only way to keep the labels distinct.

### R6 — Centring

Snapping can leave the series visually glued to one edge of the axis: the gap below
`dataMin` and the gap above `dataMax` may differ by up to a full step, which matters when
the step is large relative to the series span.

While `count < maxTicks` and `|gapLow - gapHigh| > step/2`, extend the side with the
smaller gap by one step.

The loop is bounded by `maxTicks`, so a series may remain off-centre when the tick budget
is exhausted. That is the documented trade-off: the budget wins.

### R7 — Decimals

    decimals = clamp(-floor(log10(step)), 0, maxDecimals)
    decimals = max(decimals, minDecimals)

The step determines how much precision a label needs; `minDecimals` is a floor for
instruments that are always quoted to a fixed precision, and `maxDecimals` is a ceiling
that R5 has already made safe.

### R8 — Ticks and labels

`ticks[i] = round(axisMin + i*step, decimals)` for `i` in `0 .. count-1`, each rendered as
a fixed-point string with exactly `decimals` places. Negative zero renders as `0`.

## Post-conditions

Every result must satisfy all of these. They are asserted in both test suites, on the
fixtures and on a randomised sweep.

| | Invariant |
|---|---|
| I1 | Every tick is an integer multiple of `step` |
| I2 | `axisMin <= dataMin` and `axisMax >= dataMax` |
| I3 | `step = m * 10^n` with `m` in `{1, 2, 5}` |
| I4 | `2 <= count <= maxTicks`. Two ticks occur when the series fits between adjacent multiples; three is the floor otherwise |
| I5 | No two ticks render to the same label |
| I6 | `minDecimals <= decimals <= maxDecimals` |
| I7 | `|gapLow - gapHigh| <= step/2`, or `count = maxTicks` |
| I8 | Ticks are strictly increasing and evenly spaced |

## Pseudocode

    function computeAxis(dataMin, dataMax, maxTicks, padding, minDecimals, maxDecimals):
        reject non-finite inputs, dataMax < dataMin, maxTicks < 3,
               padding < 0, minDecimals > maxDecimals

        span = dataMax - dataMin
        flat = span <= |dataMax| * 1e-12

        if flat:                                              # R1
            if dataMax == 0: lo, hi = -1, +1
            else:            half = |dataMax| * 0.001
                             lo, hi = dataMax - half, dataMax + half
        else:                                                 # R2
            pad = span * padding
            lo, hi = dataMin - pad, dataMax + pad

        minStep = 10 ^ -maxDecimals
        step    = niceStep((hi - lo) / (maxTicks - 1))        # R3

        repeat:                                               # R4, R5
            axisMin = floor(lo / step) * step
            axisMax = ceil (hi / step) * step
            while axisMin > dataMin: axisMin = axisMin - step
            while axisMax < dataMax: axisMax = axisMax + step
            count = round((axisMax - axisMin) / step) + 1
            if count <= maxTicks and step >= minStep: break
            step = nextStep(step)

        while count < maxTicks:                               # R6
            gapLow  = dataMin - axisMin
            gapHigh = axisMax - dataMax
            if |gapLow - gapHigh| <= step / 2: break
            if gapLow < gapHigh: axisMin = axisMin - step
            else:                axisMax = axisMax + step
            count = count + 1

        decimals = clamp(-floor(log10(step)), 0, maxDecimals) # R7
        decimals = max(decimals, minDecimals)

        return axisMin, axisMax, step, decimals,              # R8
               [round(axisMin + i*step, decimals) for i in 0 .. count-1]
