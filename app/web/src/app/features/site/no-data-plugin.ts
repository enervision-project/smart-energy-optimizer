import { Chart, Plugin } from 'chart.js';

/** Hatches steps without readings, so that a gap differs from zero consumption. */
export function noDataPlugin(indices: () => number[]): Plugin<'line'> {
  return {
    id: 'noData',
    beforeDatasetsDraw(chart: Chart<'line'>) {
      const gaps = indices();
      const x = chart.scales['x'];
      const count = chart.data.labels?.length ?? 0;
      if (!gaps.length || !x || !count) {
        return;
      }
      const { top, bottom, left, right } = chart.chartArea;
      const width = count > 1 ? x.getPixelForValue(1) - x.getPixelForValue(0) : right - left;
      const ctx = chart.ctx;
      ctx.save();
      ctx.fillStyle = hatch(ctx) ?? 'rgba(91, 101, 115, 0.12)';
      for (const i of gaps) {
        const start = Math.max(left, x.getPixelForValue(i) - width / 2);
        const end = Math.min(right, x.getPixelForValue(i) + width / 2);
        ctx.fillRect(start, top, end - start, bottom - top);
      }
      ctx.restore();
    },
  };
}

function hatch(ctx: CanvasRenderingContext2D): CanvasPattern | null {
  const tile = document.createElement('canvas');
  tile.width = 8;
  tile.height = 8;
  const t = tile.getContext('2d');
  if (!t) {
    return null;
  }
  t.strokeStyle = 'rgba(91, 101, 115, 0.45)';
  t.lineWidth = 1;
  t.beginPath();
  t.moveTo(0, 8);
  t.lineTo(8, 0);
  t.stroke();
  return ctx.createPattern(tile, 'repeat');
}
