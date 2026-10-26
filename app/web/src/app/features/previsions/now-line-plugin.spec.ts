import { Chart } from 'chart.js';
import { nowLinePlugin } from './now-line-plugin';

function draw(position: number | null) {
  const ctx = {
    save: vi.fn(),
    restore: vi.fn(),
    beginPath: vi.fn(),
    moveTo: vi.fn(),
    lineTo: vi.fn(),
    stroke: vi.fn(),
    fillText: vi.fn(),
  };
  const chart = {
    ctx,
    chartArea: { top: 10, bottom: 110 },
    scales: { x: { getPixelForValue: (i: number) => 100 * i } },
  } as unknown as Chart<'line'>;
  (nowLinePlugin(() => position).afterDatasetsDraw as (c: Chart<'line'>) => void)(chart);
  return ctx;
}

describe('nowLinePlugin', () => {
  it('trace le trait au bon endroit dans le pas courant', () => {
    const ctx = draw(12.25);
    expect(ctx.moveTo).toHaveBeenCalledWith(1225, 10);
    expect(ctx.lineTo).toHaveBeenCalledWith(1225, 110);
    expect(ctx.fillText).toHaveBeenCalledWith('maintenant', 1229, 22);
  });

  it('ne trace rien sans position', () => {
    expect(draw(null).moveTo).not.toHaveBeenCalled();
  });
});
