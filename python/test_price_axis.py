"""Conformance and property tests for the reference implementation."""

import json
import math
import pathlib
import random

import pytest

from price_axis import (
    AxisError,
    compute_axis,
    check_invariants,
    next_step,
    nice_step,
    SPEC_VERSION,
)

VECTORS = json.loads((pathlib.Path(__file__).resolve().parents[1] / "vectors.json").read_text())


def test_vector_file_matches_spec_version():
    assert VECTORS["spec_version"] == SPEC_VERSION


@pytest.mark.parametrize("case", VECTORS["cases"], ids=lambda c: c["name"])
def test_conformance_vectors(case):
    """The shared fixture every implementation must reproduce exactly."""
    args = dict(case["input"])
    axis = compute_axis(
        args.pop("data_min"),
        args.pop("data_max"),
        **args,
    )
    assert axis.as_dict() == case["expected"]


@pytest.mark.parametrize("case", VECTORS["cases"], ids=lambda c: c["name"])
def test_vectors_satisfy_invariants(case):
    args = dict(case["input"])
    data_min, data_max = args.pop("data_min"), args.pop("data_max")
    axis = compute_axis(data_min, data_max, **args)
    assert not check_invariants(
        axis, float(data_min), float(data_max),
        args["max_ticks"], args["min_decimals"], args["max_decimals"],
    )


# --- R3 / R5: the nice-step ladder -------------------------------------------------

@pytest.mark.parametrize("raw,expected", [
    (0.9, 1.0), (1.0, 1.0), (1.1, 2.0), (2.0, 2.0), (2.1, 5.0),
    (5.0, 5.0), (5.1, 10.0), (27.5, 50.0), (1e-7, 1e-7), (3e6, 5e6),
])
def test_nice_step(raw, expected):
    assert nice_step(raw) == pytest.approx(expected, rel=1e-12)


@pytest.mark.parametrize("step,expected", [
    (1.0, 2.0), (2.0, 5.0), (5.0, 10.0), (0.01, 0.02), (0.05, 0.1), (2e-8, 5e-8),
])
def test_next_step(step, expected):
    assert next_step(step) == pytest.approx(expected, rel=1e-12)


def test_next_step_always_grows_and_stays_nice():
    step = 1e-9
    for _ in range(40):
        nxt = next_step(step)
        assert nxt >= step * 2.0 * (1 - 1e-12)
        exp = math.floor(math.log10(nxt) + 1e-9)
        assert round(nxt / 10.0**exp, 9) in (1.0, 2.0, 5.0)
        step = nxt


# --- R1: flat market ---------------------------------------------------------------

def test_flat_market_gets_a_span_and_sits_in_the_middle():
    axis = compute_axis(42.5, 42.5)
    assert axis.flat
    assert axis.max > axis.min
    assert "42.50" in axis.labels
    below = sum(1 for t in axis.ticks if t < 42.5)
    above = sum(1 for t in axis.ticks if t > 42.5)
    assert below == above


def test_flat_zero_is_symmetric_about_zero():
    axis = compute_axis(0, 0)
    assert axis.flat
    assert axis.min == -axis.max


def test_near_flat_is_treated_as_flat():
    value = 1234.5
    axis = compute_axis(value, value + value * 1e-15)
    assert axis.flat


# --- R5: widening for renderability ------------------------------------------------

def test_step_widens_until_labels_are_distinct():
    axis = compute_axis(1.0000001, 1.0000002)
    assert axis.step >= 1e-6
    assert len(set(axis.labels)) == len(axis.labels)


def test_lowering_max_decimals_forces_a_coarser_step():
    fine = compute_axis(0.123456, 0.987654, max_decimals=6)
    coarse = compute_axis(0.123456, 0.987654, max_decimals=2)
    assert coarse.step >= fine.step
    assert coarse.decimals <= 2


# --- R7: precision floor -----------------------------------------------------------

def test_precision_floor_raises_decimals_without_changing_geometry():
    plain = compute_axis(10, 14)
    floored = compute_axis(10, 14, min_decimals=2)
    assert floored.decimals == 2
    assert floored.step == plain.step
    assert floored.ticks == plain.ticks
    assert floored.labels[0].endswith(".00")


def test_negative_zero_never_reaches_a_label():
    axis = compute_axis(-3.5, 7.25)
    assert not any(label.startswith("-0.") or label == "-0" for label in axis.labels)


# --- R6: centring ------------------------------------------------------------------

def test_tick_budget_wins_over_centring():
    """I7 may be given up, but only once the budget is exhausted."""
    axis = compute_axis(-3.5, 7.25, max_ticks=8)
    gap_low = -3.5 - axis.min
    gap_high = axis.max - 7.25
    if abs(gap_low - gap_high) > axis.step / 2:
        assert axis.count == 8


# --- rejection ---------------------------------------------------------------------

@pytest.mark.parametrize("kwargs", [
    dict(data_min=10, data_max=5),
    dict(data_min=float("nan"), data_max=1),
    dict(data_min=1, data_max=float("inf")),
    dict(data_min=1, data_max=2, max_ticks=1),
    dict(data_min=1, data_max=2, max_ticks=2),  # R5: unsatisfiable, see SPEC
    dict(data_min=1, data_max=2, padding=-0.1),
    dict(data_min=1, data_max=2, min_decimals=4, max_decimals=2),
    dict(data_min=1, data_max=2, min_decimals=-1),
    dict(data_min="10", data_max=20),
    dict(data_min=True, data_max=20),
])
def test_bad_input_is_rejected(kwargs):
    with pytest.raises(AxisError):
        compute_axis(**kwargs)


# --- the sweep ---------------------------------------------------------------------

def _random_case(rng):
    scale = 10 ** rng.uniform(-8, 8)
    centre = rng.uniform(-1, 1) * scale
    span = abs(rng.uniform(0, 1)) ** 3 * scale
    if rng.random() < 0.08:
        span = 0.0
    lo = centre - span / 2
    return lo, lo + span, {
        "max_ticks": rng.randint(3, 12),
        "padding": rng.choice([0.0, 0.02, 0.05, 0.2]),
        "min_decimals": rng.choice([0, 0, 0, 2]),
        "max_decimals": rng.choice([2, 4, 6, 6, 8]),
    }


def test_invariants_hold_across_a_random_sweep():
    rng = random.Random(20260915)
    for _ in range(20000):
        lo, hi, opts = _random_case(rng)
        if opts["min_decimals"] > opts["max_decimals"]:
            continue
        axis = compute_axis(lo, hi, **opts)
        failures = check_invariants(
            axis, lo, hi, opts["max_ticks"], opts["min_decimals"], opts["max_decimals"]
        )
        assert not failures, f"{lo!r}..{hi!r} {opts}: {failures}"


def test_result_is_deterministic():
    first = compute_axis(1234.5678, 2345.6789, max_ticks=7)
    second = compute_axis(1234.5678, 2345.6789, max_ticks=7)
    assert first == second
