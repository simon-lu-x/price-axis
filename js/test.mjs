/** Conformance and property tests. Run with: node --test js/ */

import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import {
  AxisError,
  SPEC_VERSION,
  checkInvariants,
  computeAxis,
  niceStep,
  nextStep,
} from "./price-axis.mjs";

const vectors = JSON.parse(
  readFileSync(fileURLToPath(new URL("../vectors.json", import.meta.url)), "utf8"),
);

/** vectors.json is written with Python's snake_case keys. */
function callWithVector(input) {
  return computeAxis(input.data_min, input.data_max, {
    maxTicks: input.max_ticks,
    padding: input.padding,
    minDecimals: input.min_decimals,
    maxDecimals: input.max_decimals,
  });
}

test("vector file matches the spec version", () => {
  assert.equal(vectors.spec_version, SPEC_VERSION);
});

for (const testCase of vectors.cases) {
  test(`conformance: ${testCase.name}`, () => {
    const axis = callWithVector(testCase.input);
    const expected = testCase.expected;
    // Exact equality, not approximate. Two implementations of the same spec have no
    // licence to differ in the last bit; if they do, the spec is underspecified.
    assert.equal(axis.step, expected.step, "step");
    assert.equal(axis.decimals, expected.decimals, "decimals");
    assert.equal(axis.flat, expected.flat, "flat");
    assert.deepEqual(axis.ticks, expected.ticks, "ticks");
    assert.deepEqual(axis.labels, expected.labels, "labels");
    assert.equal(axis.min, expected.min, "min");
    assert.equal(axis.max, expected.max, "max");
  });

  test(`invariants: ${testCase.name}`, () => {
    const i = testCase.input;
    const axis = callWithVector(i);
    assert.deepEqual(
      checkInvariants(axis, i.data_min, i.data_max, i.max_ticks, i.min_decimals, i.max_decimals),
      [],
    );
  });
}

test("nice step ladder", () => {
  const cases = [
    [0.9, 1], [1, 1], [1.1, 2], [2, 2], [2.1, 5],
    [5, 5], [5.1, 10], [27.5, 50], [1e-7, 1e-7], [3e6, 5e6],
  ];
  for (const [raw, expected] of cases) {
    assert.ok(Math.abs(niceStep(raw) - expected) < expected * 1e-12, `niceStep(${raw})`);
  }
});

test("next step ladder", () => {
  const cases = [[1, 2], [2, 5], [5, 10], [0.01, 0.02], [0.05, 0.1], [2e-8, 5e-8]];
  for (const [step, expected] of cases) {
    assert.ok(Math.abs(nextStep(step) - expected) < expected * 1e-12, `nextStep(${step})`);
  }
});

test("a flat series gets a span and sits in the middle", () => {
  const axis = computeAxis(42.5, 42.5);
  assert.ok(axis.flat);
  assert.ok(axis.max > axis.min);
  assert.ok(axis.labels.includes("42.50"));
  const below = axis.ticks.filter((t) => t < 42.5).length;
  const above = axis.ticks.filter((t) => t > 42.5).length;
  assert.equal(below, above);
});

test("the step widens until labels are distinct", () => {
  const axis = computeAxis(1.0000001, 1.0000002);
  assert.ok(axis.step >= 1e-6);
  assert.equal(new Set(axis.labels).size, axis.labels.length);
});

test("the precision floor lifts decimals without moving the ticks", () => {
  const plain = computeAxis(10, 14);
  const floored = computeAxis(10, 14, { minDecimals: 2 });
  assert.equal(floored.decimals, 2);
  assert.equal(floored.step, plain.step);
  assert.deepEqual(floored.ticks, plain.ticks);
  assert.ok(floored.labels[0].endsWith(".00"));
});

test("negative zero never reaches a label", () => {
  const axis = computeAxis(-3.5, 7.25);
  assert.ok(!axis.labels.some((l) => l.startsWith("-0.") || l === "-0"));
});

test("bad input is rejected", () => {
  const bad = [
    [10, 5, {}],
    [NaN, 1, {}],
    [1, Infinity, {}],
    [1, 2, { maxTicks: 2 }],
    [1, 2, { maxTicks: 4.5 }],
    [1, 2, { padding: -0.1 }],
    [1, 2, { minDecimals: 4, maxDecimals: 2 }],
    [1, 2, { minDecimals: -1 }],
    ["10", 20, {}],
  ];
  for (const [lo, hi, opts] of bad) {
    assert.throws(() => computeAxis(lo, hi, opts), AxisError, `${lo}..${hi} ${JSON.stringify(opts)}`);
  }
});

/** Deterministic PRNG so a failure can be reproduced from the seed alone. */
function mulberry32(seed) {
  return function next() {
    seed |= 0;
    seed = (seed + 0x6d2b79f5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

test("invariants hold across a random sweep", () => {
  const rand = mulberry32(20260915);
  const pick = (choices) => choices[Math.floor(rand() * choices.length)];
  for (let i = 0; i < 20000; i += 1) {
    const scale = Math.pow(10, rand() * 16 - 8);
    const centre = (rand() * 2 - 1) * scale;
    let span = Math.pow(rand(), 3) * scale;
    if (rand() < 0.08) span = 0;
    const lo = centre - span / 2;
    const hi = lo + span;
    const opts = {
      maxTicks: 3 + Math.floor(rand() * 10),
      padding: pick([0, 0.02, 0.05, 0.2]),
      minDecimals: pick([0, 0, 0, 2]),
      maxDecimals: pick([2, 4, 6, 6, 8]),
    };
    if (opts.minDecimals > opts.maxDecimals) continue;
    const axis = computeAxis(lo, hi, opts);
    const failures = checkInvariants(
      axis, lo, hi, opts.maxTicks, opts.minDecimals, opts.maxDecimals,
    );
    assert.deepEqual(failures, [], `${lo}..${hi} ${JSON.stringify(opts)}`);
  }
});
