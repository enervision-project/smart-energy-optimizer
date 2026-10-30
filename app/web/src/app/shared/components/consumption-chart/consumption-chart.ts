import { Component, computed, input } from '@angular/core';
import { ChartData, ChartOptions } from 'chart.js';
import { BaseChartDirective } from 'ng2-charts';

const CONSUMPTION_COLOR = '#1f7a63';
const FLAGGED_COLOR = '#d08c2b';
const CAPACITY_COLOR = '#b23a48';

/** `null` values stay gaps (`spanGaps: false`). */
@Component({
  imports: [BaseChartDirective],
  selector: 'app-consumption-chart',
  styleUrl: './consumption-chart.scss',
  templateUrl: './consumption-chart.html',
})
export class ConsumptionChart {
  readonly labels = input.required<string[]>();
  readonly values = input.required<(number | null)[]>();
  readonly capacity = input<number | null>(null);
  readonly flagged = input<boolean[]>([]);
  readonly description = input.required<string>();

  protected readonly data = computed<ChartData<'line', (number | null)[], string>>(() => {
    const flagged = this.flagged();
    const capacity = this.capacity();
    return {
      labels: this.labels(),
      datasets: [
        {
          label: 'Consommation',
          data: this.values(),
          borderColor: CONSUMPTION_COLOR,
          backgroundColor: CONSUMPTION_COLOR,
          borderWidth: 2,
          pointRadius: this.values().map((_, i) => (flagged[i] ? 3 : 0)),
          pointBackgroundColor: FLAGGED_COLOR,
          pointBorderColor: FLAGGED_COLOR,
          spanGaps: false,
        },
        {
          label: 'Capacité',
          data: this.labels().map(() => capacity),
          borderColor: CAPACITY_COLOR,
          backgroundColor: CAPACITY_COLOR,
          borderDash: [2, 4],
          borderWidth: 1.5,
          pointRadius: 0,
          hidden: capacity === null,
        },
      ],
    };
  });

  protected readonly options: ChartOptions<'line'> = {
    responsive: true,
    maintainAspectRatio: false,
    animation: false,
    interaction: { mode: 'index', intersect: false },
    scales: {
      x: { ticks: { maxTicksLimit: 9, maxRotation: 0 } },
      y: { beginAtZero: true, title: { display: true, text: 'kW' } },
    },
    plugins: {
      legend: { position: 'bottom' },
    },
  };
}
