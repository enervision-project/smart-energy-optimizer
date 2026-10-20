import { Component, input } from '@angular/core';

@Component({
  imports: [],
  selector: 'app-kpi-card',
  styleUrl: './kpi-card.scss',
  templateUrl: './kpi-card.html',
})
export class KpiCard {
  readonly label = input.required<string>();
  readonly value = input.required<string>();
  readonly detail = input<string>();
}
