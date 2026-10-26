import { Chart } from 'chart.js';
import { noDataPlugin } from './no-data-plugin';

/** Graphique minimal : 4 pas de 100 px, zone de tracé de 0 à 400 px. */
function fakeChart(labels: number) {
  const fillRect = vi.fn();
  const ctx = {
    save: vi.fn(),
    restore: vi.fn(),
    fillRect,
    createPattern: vi.fn(() => null),
    fillStyle: '',
  };
  const chart = {
    ctx,
    chartArea: { top: 10, bottom: 110, left: 0, right: 400 },
    data: { labels: Array.from({ length: labels }, (_, i) => String(i)) },
    scales: { x: { getPixelForValue: (i: number) => 50 + 100 * i } },
  } as unknown as Chart<'line'>;
  return { chart, fillRect };
}

function draw(indices: number[], labels = 4) {
  const { chart, fillRect } = fakeChart(labels);
  const plugin = noDataPlugin(() => indices);
  (plugin.beforeDatasetsDraw as (c: Chart<'line'>) => void)(chart);
  return fillRect;
}

describe('noDataPlugin', () => {
  it('hachure toute la hauteur des pas sans mesure', () => {
    const fillRect = draw([1, 3]);
    expect(fillRect).toHaveBeenCalledWith(100, 10, 100, 100);
    expect(fillRect).toHaveBeenCalledWith(300, 10, 100, 100);
  });

  it('ne dessine rien sans pas vide ou sans données', () => {
    expect(draw([])).not.toHaveBeenCalled();
    expect(draw([0], 0)).not.toHaveBeenCalled();
  });
});
