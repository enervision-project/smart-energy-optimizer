import { Component, computed, input } from '@angular/core';

const WIDTH = 100;
const HEIGHT = 24;

@Component({
  imports: [],
  selector: 'app-sparkline',
  styleUrl: './sparkline.scss',
  templateUrl: './sparkline.html',
})
export class Sparkline {
  readonly values = input.required<(number | null)[]>();
  readonly description = input.required<string>();

  protected readonly width = WIDTH;
  protected readonly height = HEIGHT;

  protected readonly path = computed(() => {
    const values = this.values();
    const known = values.filter((v): v is number => v !== null);
    if (!known.length) {
      return '';
    }
    const min = Math.min(...known);
    const range = Math.max(...known) - min || 1;
    const step = values.length > 1 ? WIDTH / (values.length - 1) : 0;
    let path = '';
    let drawing = false;
    values.forEach((v, i) => {
      if (v === null) {
        drawing = false;
        return;
      }
      const x = (i * step).toFixed(1);
      const y = (HEIGHT - 2 - ((v - min) / range) * (HEIGHT - 4)).toFixed(1);
      path += `${drawing ? 'L' : 'M'}${x} ${y} `;
      drawing = true;
    });
    return path.trim();
  });
}
