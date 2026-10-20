import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideCharts, withDefaultRegisterables } from 'ng2-charts';
import { ConsumptionChart } from './consumption-chart';

describe('ConsumptionChart', () => {
  let fixture: ComponentFixture<ConsumptionChart>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [ConsumptionChart],
      providers: [provideCharts(withDefaultRegisterables())],
    }).compileComponents();

    fixture = TestBed.createComponent(ConsumptionChart);
    fixture.componentRef.setInput('labels', ['10:00', '11:00']);
    fixture.componentRef.setInput('values', [120, null]);
    fixture.componentRef.setInput('description', 'Courbe de test');
  });

  it('décrit la courbe pour les lecteurs d’écran', async () => {
    await fixture.whenStable();
    const canvas = (fixture.nativeElement as HTMLElement).querySelector('canvas');
    expect(canvas?.getAttribute('aria-label')).toBe('Courbe de test');
  });
});
