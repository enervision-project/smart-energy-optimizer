import { ComponentFixture, TestBed } from '@angular/core/testing';
import { ConsumptionChart } from './consumption-chart';

describe('ConsumptionChart', () => {
  let component: ConsumptionChart;
  let fixture: ComponentFixture<ConsumptionChart>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [ConsumptionChart],
    }).compileComponents();

    fixture = TestBed.createComponent(ConsumptionChart);
    component = fixture.componentInstance;
    await fixture.whenStable();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});
