export interface SparklinePaths {
  linePath: string;
  areaPath: string;
}

export function createSparklinePaths(
  values: readonly number[],
  width: number,
  height: number,
  inset = 3
): SparklinePaths {
  const source = values.length > 0 ? values : [10, 14, 12, 18, 16, 22];
  const baseline = Math.min(...source);
  const padded = [
    ...Array(Math.max(0, 6 - source.length)).fill(baseline),
    ...source,
  ];
  const min = Math.min(...padded);
  const max = Math.max(...padded);
  const span = Math.max(1, max - min);
  const points = padded.map((value, index) => ({
    x: (index / Math.max(1, padded.length - 1)) * width,
    y: height - inset - ((value - min) / span) * (height - inset * 2),
  }));

  let linePath = `M ${points[0].x.toFixed(1)} ${points[0].y.toFixed(1)}`;
  for (let index = 0; index < points.length - 1; index += 1) {
    const previous = points[Math.max(0, index - 1)];
    const start = points[index];
    const end = points[index + 1];
    const next = points[Math.min(points.length - 1, index + 2)];
    const cp1x = start.x + (end.x - previous.x) / 6;
    const cp1y = start.y + (end.y - previous.y) / 6;
    const cp2x = end.x - (next.x - start.x) / 6;
    const cp2y = end.y - (next.y - start.y) / 6;
    linePath += ` C ${cp1x.toFixed(1)} ${cp1y.toFixed(1)}, ${cp2x.toFixed(1)} ${cp2y.toFixed(1)}, ${end.x.toFixed(1)} ${end.y.toFixed(1)}`;
  }

  const first = points[0];
  const last = points[points.length - 1];
  return {
    linePath,
    areaPath: `${linePath} L ${last.x.toFixed(1)} ${height} L ${first.x.toFixed(1)} ${height} Z`,
  };
}
