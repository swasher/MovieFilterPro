export type WeightMap = Record<string, number>;

const TOTAL = 100;

function clampWeight(value: number): number {
  return Math.max(0, Math.min(TOTAL, Math.round(value)));
}

/** Делит сумму на count частей так, чтобы сумма частей была ровно amount. */
function splitEvenly(amount: number, count: number): number[] {
  if (count <= 0) return [];
  const base = Math.floor(amount / count);
  const remainder = amount - base * count;
  return Array.from({ length: count }, (_, index) => base + (index < remainder ? 1 : 0));
}

/**
 * Меняет один вес так, чтобы сумма всех весов осталась 100.
 *
 * Уменьшение: освободившиеся проценты отдаём самым маленьким весам
 * (если минимум делят несколько — поровну).
 * Увеличение: проценты забираем у самых больших весов; если у максимума
 * не хватает запаса, остаток забираем у следующего по величине.
 */
export function redistributeWeights(
  weights: WeightMap,
  key: string,
  nextValue: number
): WeightMap {
  const result: WeightMap = { ...weights };
  const others = Object.keys(result).filter((item) => item !== key);
  const target = clampWeight(nextValue);
  const current = result[key] ?? 0;
  let delta = target - current;

  result[key] = target;
  if (!delta || !others.length) return result;

  if (delta < 0) {
    const min = Math.min(...others.map((item) => result[item] ?? 0));
    const smallest = others.filter((item) => (result[item] ?? 0) === min);
    const shares = splitEvenly(-delta, smallest.length);
    smallest.forEach((item, index) => {
      result[item] = (result[item] ?? 0) + shares[index];
    });
    return result;
  }

  while (delta > 0) {
    const max = Math.max(...others.map((item) => result[item] ?? 0));
    if (max <= 0) break;
    const largest = others.filter((item) => (result[item] ?? 0) === max);
    const capacity = max * largest.length;
    if (delta >= capacity) {
      for (const item of largest) result[item] = 0;
      delta -= capacity;
      continue;
    }
    const shares = splitEvenly(delta, largest.length);
    largest.forEach((item, index) => {
      result[item] = (result[item] ?? 0) - shares[index];
    });
    delta = 0;
  }

  return result;
}

/**
 * Приводит набор весов к сумме 100 (нужно для ссылок, сохранённых до
 * появления правила «сумма всегда 100»). Нулевая сумма заменяется fallback.
 */
export function normalizeWeights(
  weights: WeightMap,
  keys: string[],
  fallback: WeightMap
): WeightMap {
  const values = keys.map((key) => clampWeight(weights[key] ?? 0));
  const total = values.reduce((sum, value) => sum + value, 0);

  if (total <= 0) {
    return Object.fromEntries(keys.map((key) => [key, fallback[key] ?? 0]));
  }
  if (total === TOTAL) {
    return Object.fromEntries(keys.map((key, index) => [key, values[index]]));
  }

  const exact = values.map((value) => (value * TOTAL) / total);
  const result = exact.map((value) => Math.floor(value));
  let remainder = TOTAL - result.reduce((sum, value) => sum + value, 0);

  const order = exact
    .map((value, index) => ({ index, fraction: value - result[index] }))
    .sort((left, right) => right.fraction - left.fraction);

  for (let index = 0; remainder > 0; index += 1, remainder -= 1) {
    result[order[index % order.length].index] += 1;
  }

  return Object.fromEntries(keys.map((key, index) => [key, result[index]]));
}
