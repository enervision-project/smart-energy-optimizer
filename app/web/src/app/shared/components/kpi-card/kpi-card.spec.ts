import { ComponentFixture, TestBed } from '@angular/core/testing';
import { KpiCard } from './kpi-card';

describe('KpiCard', () => {
  let fixture: ComponentFixture<KpiCard>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [KpiCard],
    }).compileComponents();

    fixture = TestBed.createComponent(KpiCard);
    fixture.componentRef.setInput('label', 'Charge moyenne');
    fixture.componentRef.setInput('value', '44,6 %');
  });

  it('affiche le libellé et la valeur', async () => {
    await fixture.whenStable();
    const el = fixture.nativeElement as HTMLElement;
    expect(el.querySelector('.label')?.textContent).toBe('Charge moyenne');
    expect(el.querySelector('.value')?.textContent).toBe('44,6 %');
    expect(el.querySelector('.detail')).toBeNull();
  });

  it('affiche le détail quand il est fourni', async () => {
    fixture.componentRef.setInput('detail', 'capacité 4 130 kW');
    await fixture.whenStable();
    const el = fixture.nativeElement as HTMLElement;
    expect(el.querySelector('.detail')?.textContent).toBe('capacité 4 130 kW');
  });
});
