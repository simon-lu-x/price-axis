"""Deterministic y-axis ticks for price charts.

Reference implementation of SPEC.md. Standard library only.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence

SPEC_VERSION = "1.0.0"

MANTISSAS = (1.0, 2.0, 5.0)
DEFAULT_MAX_TICKS = 8
DEFAULT_PADDING = 0.05
DEFAULT_MAX_DECIMALS = 6
FLAT_RATIO = 0.001
ZERO_SPAN = 1.0

_EPS = 1e-12
_LOG_NUDGE = 1e-9


class AxisError(ValueError):
    """The inputs cannot produce a valid axis. Reject, never repair."""


@dataclass(frozen=True)
class Axis:
    min: float
    max: float
    step: float
    decimals: int
    ticks: tuple
    labels: tuple
    flat: bool

    @property
    def count(self) -> int:
        return len(self.ticks)

    def as_dict(self) -> dict:
        return {
            "min": self.min,
            "max": self.max,
            "step": self.step,
            "decimals": self.decimals,
            "ticks": list(self.ticks),
            "labels": list(self.labels),
            "flat": self.flat,
        }


def _pow10(exp: int) -> float:
    """10**exp via the decimal literal.

    `_pow10(exp)` is a library pow and is not guaranteed to be the correctly rounded
    double for every exponent, so two languages can disagree in the last bit. Parsing
    the literal is correctly rounded everywhere, which keeps the implementations
    bit-identical. The JavaScript port uses Number("1e" + exp) for the same reason.
    """
    return float(f"1e{exp}")


def _exponent(value: float) -> int:
    """Base-10 exponent of a positive nice step, robust to log10 fuzz."""
    return math.floor(math.log10(value) + _LOG_NUDGE)


def nice_step(raw: float) -> float:
    """Smallest step of the form m*10^n, m in {1,2,5}, that is >= raw. R3."""
    if not math.isfinite(raw) or raw <= 0.0:
        raise AxisError(f"raw step must be finite and positive, got {raw!r}")
    exp = math.floor(math.log10(raw))
    for mantissa in MANTISSAS:
        candidate = mantissa * _pow10(exp)
        if candidate >= raw * (1.0 - _EPS):
            return candidate
    return _pow10(exp + 1)


def next_step(step: float) -> float:
    """The next nice step up: 1 -> 2 -> 5 -> 10. R5."""
    if not math.isfinite(step) or step <= 0.0:
        raise AxisError(f"step must be finite and positive, got {step!r}")
    exp = _exponent(step)
    mantissa = step / _pow10(exp)
    if mantissa < 1.5:
        return 2.0 * _pow10(exp)
    if mantissa < 3.5:
        return 5.0 * _pow10(exp)
    return _pow10(exp + 1)


def _check_number(name: str, value) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AxisError(f"{name} must be a number, got {value!r}")
    value = float(value)
    if not math.isfinite(value):
        raise AxisError(f"{name} must be finite, got {value!r}")
    return value


def compute_axis(
    data_min,
    data_max,
    *,
    max_ticks: int = DEFAULT_MAX_TICKS,
    padding: float = DEFAULT_PADDING,
    min_decimals: int = 0,
    max_decimals: int = DEFAULT_MAX_DECIMALS,
) -> Axis:
    """Compute the axis for a price series. See SPEC.md."""
    data_min = _check_number("data_min", data_min)
    data_max = _check_number("data_max", data_max)
    padding = _check_number("padding", padding)

    if data_max < data_min:
        raise AxisError(f"data_max {data_max!r} is below data_min {data_min!r}")
    if not isinstance(max_ticks, int) or isinstance(max_ticks, bool) or max_ticks < 3:
        raise AxisError(f"max_ticks must be an integer >= 3, got {max_ticks!r}")
    if padding < 0.0:
        raise AxisError(f"padding must not be negative, got {padding!r}")
    for name, value in (("min_decimals", min_decimals), ("max_decimals", max_decimals)):
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise AxisError(f"{name} must be a non-negative integer, got {value!r}")
    if min_decimals > max_decimals:
        raise AxisError(
            f"min_decimals {min_decimals} exceeds max_decimals {max_decimals}"
        )
    if max_decimals > 15:
        raise AxisError(f"max_decimals must be <= 15, got {max_decimals}")

    span = data_max - data_min
    flat = span <= abs(data_max) * _EPS

    if flat:  # R1
        if data_max == 0.0:
            lo, hi = -ZERO_SPAN, ZERO_SPAN
        else:
            half = abs(data_max) * FLAT_RATIO
            lo, hi = data_max - half, data_max + half
    else:  # R2
        pad = span * padding
        lo, hi = data_min - pad, data_max + pad

    min_step = _pow10(-max_decimals)
    step = nice_step((hi - lo) / (max_ticks - 1))

    axis_min = axis_max = 0.0
    count = 0
    for _ in range(128):  # R4, R5
        axis_min = math.floor(lo / step) * step
        axis_max = math.ceil(hi / step) * step
        while axis_min > data_min:
            axis_min -= step
        while axis_max < data_max:
            axis_max += step
        count = int(round((axis_max - axis_min) / step)) + 1
        if count <= max_ticks and step >= min_step * (1.0 - _EPS):
            break
        step = next_step(step)
    else:  # pragma: no cover - unreachable, the step at least doubles each pass
        raise AxisError("no tick solution found")

    while count < max_ticks:  # R6
        gap_low = data_min - axis_min
        gap_high = axis_max - data_max
        if abs(gap_low - gap_high) <= step / 2.0 * (1.0 + _EPS):
            break
        if gap_low < gap_high:
            axis_min -= step
        else:
            axis_max += step
        count += 1

    decimals = -_exponent(step)  # R7
    decimals = max(0, min(decimals, max_decimals))
    decimals = max(decimals, min_decimals)

    ticks = []
    labels = []
    for index in range(count):  # R8
        value = round(axis_min + index * step, decimals)
        if value == 0.0:
            value = 0.0  # collapse -0.0
        ticks.append(value)
        labels.append(f"{value:.{decimals}f}")

    return Axis(
        min=ticks[0],
        max=ticks[-1],
        step=step,
        decimals=decimals,
        ticks=tuple(ticks),
        labels=tuple(labels),
        flat=flat,
    )


def check_invariants(
    axis: Axis,
    data_min: float,
    data_max: float,
    max_ticks: int,
    min_decimals: int,
    max_decimals: int,
) -> Sequence[str]:
    """Return the post-conditions of SPEC.md that this axis violates."""
    failures = []
    step = axis.step
    tol = step * 1e-9

    for tick in axis.ticks:
        # Tolerance has to scale with the tick, not the step: at a magnitude of 1e6 with a
        # step of 1e-6 the ratio alone consumes twelve of a double's sixteen digits.
        slack = max(abs(tick), step) * 1e-11
        if abs(tick - round(tick / step) * step) > slack:
            failures.append(f"I1 tick {tick} is not a multiple of {step}")
            break
    if axis.min > data_min + tol or axis.max < data_max - tol:
        failures.append(f"I2 axis [{axis.min}, {axis.max}] misses [{data_min}, {data_max}]")
    mantissa = step / _pow10(_exponent(step))
    if not any(abs(mantissa - m) < 1e-9 for m in MANTISSAS):
        failures.append(f"I3 step {step} is not 1, 2 or 5 times a power of ten")
    if not 2 <= axis.count <= max_ticks:
        failures.append(f"I4 tick count {axis.count} outside [2, {max_ticks}]")
    if len(set(axis.labels)) != len(axis.labels):
        failures.append(f"I5 duplicate labels in {axis.labels}")
    if not min_decimals <= axis.decimals <= max_decimals:
        failures.append(f"I6 decimals {axis.decimals} outside [{min_decimals}, {max_decimals}]")
    gap_low = data_min - axis.min
    gap_high = axis.max - data_max
    if abs(gap_low - gap_high) > step / 2.0 * (1.0 + 1e-9) and axis.count != max_ticks:
        failures.append(
            f"I7 gaps {gap_low} and {gap_high} differ by more than half a step "
            f"with room to spare ({axis.count} of {max_ticks} ticks)"
        )
    for i in range(1, axis.count):
        delta = axis.ticks[i] - axis.ticks[i - 1]
        if delta <= 0 or abs(delta - step) > max(tol, _pow10(-axis.decimals) / 2):
            failures.append(f"I8 spacing {delta} at index {i} is not a clean {step}")
            break
    return failures
