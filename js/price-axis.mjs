/**
 * Deterministic y-axis ticks for price charts.
 *
 * Independent implementation of SPEC.md. No dependencies. It shares no code with the
 * Python reference; vectors.json is the only thing the two have in common.
 */

export const SPEC_VERSION = "1.0.0";

const MANTISSAS = [1, 2, 5];
const DEFAULT_MAX_TICKS = 8;
const DEFAULT_PADDING = 0.05;
const DEFAULT_MAX_DECIMALS = 6;
const FLAT_RATIO = 0.001;
const ZERO_SPAN = 1;

const EPS = 1e-12;
const LOG_NUDGE = 1e-9;

export class AxisError extends Error {
  constructor(message) {
    super(message);
    this.name = "AxisError";
  }
}

/**
 * 10**exp via the decimal literal. Math.pow is not guaranteed to return the correctly
 * rounded double for every exponent, so it can disagree with another language in the
 * last bit. The Python reference uses float(f"1e{exp}") for the same reason.
 */
function pow10(exp) {
  return Number(`1e${exp}`);
}

function exponentOf(value) {
  return Math.floor(Math.log10(value) + LOG_NUDGE);
}

/** Smallest step of the form m*10^n, m in {1,2,5}, that is >= raw. R3. */
export function niceStep(raw) {
  if (!Number.isFinite(raw) || raw <= 0) {
    throw new AxisError(`raw step must be finite and positive, got ${raw}`);
  }
  const exp = Math.floor(Math.log10(raw));
  for (const mantissa of MANTISSAS) {
    const candidate = mantissa * pow10(exp);
    if (candidate >= raw * (1 - EPS)) return candidate;
  }
  return pow10(exp + 1);
}

/** The next nice step up: 1 -> 2 -> 5 -> 10. R5. */
export function nextStep(step) {
  if (!Number.isFinite(step) || step <= 0) {
    throw new AxisError(`step must be finite and positive, got ${step}`);
  }
  const exp = exponentOf(step);
  const mantissa = step / pow10(exp);
  if (mantissa < 1.5) return 2 * pow10(exp);
  if (mantissa < 3.5) return 5 * pow10(exp);
  return pow10(exp + 1);
}

function checkNumber(name, value) {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    throw new AxisError(`${name} must be a finite number, got ${value}`);
  }
  return value;
}

function checkCount(name, value, minimum) {
  if (!Number.isInteger(value) || value < minimum) {
    throw new AxisError(`${name} must be an integer >= ${minimum}, got ${value}`);
  }
  return value;
}

/**
 * Compute the axis for a price series. See SPEC.md.
 *
 * @returns {{min:number, max:number, step:number, decimals:number,
 *            ticks:number[], labels:string[], flat:boolean}}
 */
export function computeAxis(dataMin, dataMax, options = {}) {
  const {
    maxTicks = DEFAULT_MAX_TICKS,
    padding = DEFAULT_PADDING,
    minDecimals = 0,
    maxDecimals = DEFAULT_MAX_DECIMALS,
  } = options;

  checkNumber("dataMin", dataMin);
  checkNumber("dataMax", dataMax);
  checkNumber("padding", padding);

  if (dataMax < dataMin) {
    throw new AxisError(`dataMax ${dataMax} is below dataMin ${dataMin}`);
  }
  checkCount("maxTicks", maxTicks, 3);
  if (padding < 0) throw new AxisError(`padding must not be negative, got ${padding}`);
  checkCount("minDecimals", minDecimals, 0);
  checkCount("maxDecimals", maxDecimals, 0);
  if (minDecimals > maxDecimals) {
    throw new AxisError(`minDecimals ${minDecimals} exceeds maxDecimals ${maxDecimals}`);
  }
  if (maxDecimals > 15) {
    throw new AxisError(`maxDecimals must be <= 15, got ${maxDecimals}`);
  }

  const span = dataMax - dataMin;
  const flat = span <= Math.abs(dataMax) * EPS;

  let lo;
  let hi;
  if (flat) {
    // R1
    if (dataMax === 0) {
      lo = -ZERO_SPAN;
      hi = ZERO_SPAN;
    } else {
      const half = Math.abs(dataMax) * FLAT_RATIO;
      lo = dataMax - half;
      hi = dataMax + half;
    }
  } else {
    // R2
    const pad = span * padding;
    lo = dataMin - pad;
    hi = dataMax + pad;
  }

  const minStep = pow10(-maxDecimals);
  let step = niceStep((hi - lo) / (maxTicks - 1));

  let axisMin = 0;
  let axisMax = 0;
  let count = 0;
  let solved = false;
  for (let attempt = 0; attempt < 128; attempt += 1) {
    // R4, R5
    axisMin = Math.floor(lo / step) * step;
    axisMax = Math.ceil(hi / step) * step;
    while (axisMin > dataMin) axisMin -= step;
    while (axisMax < dataMax) axisMax += step;
    count = Math.round((axisMax - axisMin) / step) + 1;
    if (count <= maxTicks && step >= minStep * (1 - EPS)) {
      solved = true;
      break;
    }
    step = nextStep(step);
  }
  if (!solved) throw new AxisError("no tick solution found");

  while (count < maxTicks) {
    // R6
    const gapLow = dataMin - axisMin;
    const gapHigh = axisMax - dataMax;
    if (Math.abs(gapLow - gapHigh) <= (step / 2) * (1 + EPS)) break;
    if (gapLow < gapHigh) axisMin -= step;
    else axisMax += step;
    count += 1;
  }

  let decimals = -exponentOf(step); // R7
  decimals = Math.max(0, Math.min(decimals, maxDecimals));
  decimals = Math.max(decimals, minDecimals);

  const factor = pow10(decimals);
  const ticks = [];
  const labels = [];
  for (let index = 0; index < count; index += 1) {
    // R8
    let value = Math.round((axisMin + index * step) * factor) / factor;
    if (value === 0) value = 0; // collapse -0
    ticks.push(value);
    labels.push(value.toFixed(decimals));
  }

  return {
    min: ticks[0],
    max: ticks[ticks.length - 1],
    step,
    decimals,
    ticks,
    labels,
    flat,
  };
}

/** Return the post-conditions of SPEC.md that this axis violates. */
export function checkInvariants(axis, dataMin, dataMax, maxTicks, minDecimals, maxDecimals) {
  const failures = [];
  const { step } = axis;
  const tol = step * 1e-9;

  for (const tick of axis.ticks) {
    const slack = Math.max(Math.abs(tick), step) * 1e-11;
    if (Math.abs(tick - Math.round(tick / step) * step) > slack) {
      failures.push(`I1 tick ${tick} is not a multiple of ${step}`);
      break;
    }
  }
  if (axis.min > dataMin + tol || axis.max < dataMax - tol) {
    failures.push(`I2 axis [${axis.min}, ${axis.max}] misses [${dataMin}, ${dataMax}]`);
  }
  const mantissa = step / pow10(exponentOf(step));
  if (!MANTISSAS.some((m) => Math.abs(mantissa - m) < 1e-9)) {
    failures.push(`I3 step ${step} is not 1, 2 or 5 times a power of ten`);
  }
  if (!(axis.ticks.length >= 2 && axis.ticks.length <= maxTicks)) {
    failures.push(`I4 tick count ${axis.ticks.length} outside [2, ${maxTicks}]`);
  }
  if (new Set(axis.labels).size !== axis.labels.length) {
    failures.push(`I5 duplicate labels in ${axis.labels.join(", ")}`);
  }
  if (!(axis.decimals >= minDecimals && axis.decimals <= maxDecimals)) {
    failures.push(`I6 decimals ${axis.decimals} outside [${minDecimals}, ${maxDecimals}]`);
  }
  const gapLow = dataMin - axis.min;
  const gapHigh = axis.max - dataMax;
  if (
    Math.abs(gapLow - gapHigh) > (step / 2) * (1 + 1e-9) &&
    axis.ticks.length !== maxTicks
  ) {
    failures.push(
      `I7 gaps ${gapLow} and ${gapHigh} differ by more than half a step with room to spare`,
    );
  }
  for (let i = 1; i < axis.ticks.length; i += 1) {
    const delta = axis.ticks[i] - axis.ticks[i - 1];
    if (delta <= 0 || Math.abs(delta - step) > Math.max(tol, pow10(-axis.decimals) / 2)) {
      failures.push(`I8 spacing ${delta} at index ${i} is not a clean ${step}`);
      break;
    }
  }
  return failures;
}
