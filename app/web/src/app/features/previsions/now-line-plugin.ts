import { Chart, Plugin } from 'chart.js';

/**
 * Trait vertical « maintenant » : sépare le mesuré de la prévision. `position` donne l'index (fractionnaire)
 * du pas courant sur l'axe des abscisses, relu à chaque dessin ; `null` = pas de trait.
 */
export function nowLinePlugin(position: () => number | null): Plugin<'line'> {
  return {
    id: 'nowLine',
    afterDatasetsDraw(chart: Chart<'line'>) {
      const index = position();
      const x = chart.scales['x'];
      if (index === null || !x) {
        return;
      }
      const { top, bottom } = chart.chartArea;
      const left = x.getPixelForValue(Math.floor(index));
      const next = x.getPixelForValue(Math.floor(index) + 1);
      const at = left + (next - left) * (index - Math.floor(index));
      const ctx = chart.ctx;
      ctx.save();
      ctx.strokeStyle = '#1f2a37';
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(at, top);
      ctx.lineTo(at, bottom);
      ctx.stroke();
      ctx.fillStyle = '#1f2a37';
      ctx.font = '12px system-ui, sans-serif';
      ctx.fillText('maintenant', at + 4, top + 12);
      ctx.restore();
    },
  };
}
