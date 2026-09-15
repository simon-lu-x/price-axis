# price-axis

Pick the y-axis for a price chart: the bounds, the tick step, the tick values, and the
number of decimal places to render them with.

A chart axis is the part of a product where the only feedback you ever get is "it looks
wrong." This repository is the other half of that sentence: the rules written down
precisely enough that someone else can implement them and you can check whether they did.

- **[SPEC.md](SPEC.md)** — eight rules and eight post-conditions, with pseudocode
- **[demo](demo/index.html)** — change the range, watch the rules and the post-conditions
  resolve live
- **[python/](python/price_axis.py)** and **[js/](js/price-axis.mjs)** — two implementations
  that share no code
- **[vectors.json](vectors.json)** — the conformance fixture both of them must reproduce

## Why two implementations

A specification is only as good as the agreement it produces between people who never
spoke to each other. The Python and JavaScript versions here were written against
SPEC.md and share nothing but `vectors.json`; both test suites assert **exact** equality
against it, not approximate. If they ever diverge in the last bit, the spec was
underspecified and the spec is what gets fixed.

## Run it

    # reference implementation, 72 tests including a 20,000-case sweep
    python3 -m pytest python/ -q

    # independent port, 43 tests including its own sweep
    node --test js/test.mjs

    # the demo needs a server, because it loads the module from ../js
    python3 -m http.server 8000     # then open localhost:8000/demo/

No dependencies beyond `pytest` and a Node with `node:test` (18+).

## What the rules do

| | |
|---|---|
| R1 | A flat series has no span to scale to, so one is synthesised and the value is centred |
| R2 | Symmetric padding above and below |
| R3 | Ticks land on `1`, `2` or `5` times a power of ten |
| R4 | Bounds snap outward to multiples of the step; covering the data is a hard post-condition |
| R5 | The step widens until the ticks both fit the budget and can be rendered distinctly |
| R6 | The series is centred within the axis while ticks remain in the budget |
| R7 | `decimals = clamp(-floor(log10(step)), 0, maxDecimals)`, then lifted to the floor |
| R8 | Ticks are emitted rounded, negative zero collapsed |

R5 is the one that earns its keep. A step of `2e-8` under `maxDecimals = 6` would render
several ticks as the same string; widening until the labels are distinct is the only fix
that keeps every other rule intact.

## Found by the tests, not by reasoning

The randomised sweep rejected an earlier draft that accepted `maxTicks = 2`. Because R4
snaps both bounds outward, widening the step drives the count down to three and stops
there — one multiple below the series, one above, and the one between. Two ticks happen
only when the series falls between adjacent multiples, so a budget of two cannot be
honoured in general. It is now a precondition, documented in R5.

## Known limits

- **Precision against magnitude.** A double carries about sixteen significant digits.
  Asking for a price near `1e7` at eight decimals spends all of them, and the guarantees
  degrade to whatever the float can represent. The spec does not pretend otherwise.
- **`maxDecimals` too low for the data.** A micro-cap price under the default ceiling of
  six decimals forces a step so coarse the axis can reach below zero. That is R5 working
  as specified; the remedy is to raise `maxDecimals`, and both settings are in the
  fixtures (`micro_cap_token`, `micro_cap_deep`) so the trade-off stays visible.
- **Linear scale only.** No log axis.

## Licence

MIT.
