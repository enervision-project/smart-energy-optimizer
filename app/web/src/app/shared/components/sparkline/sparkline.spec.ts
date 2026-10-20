import { ComponentFixture, TestBed } from '@angular/core/testing';
import { Sparkline } from './sparkline';

describe('Sparkline', () => {
  let fixture: ComponentFixture<Sparkline>;

  async function pathFor(values: (number | null)[]): Promise<string | null | undefined> {
    fixture.componentRef.setInput('values', values);
    await fixture.whenStable();
    return (fixture.nativeElement as HTMLElement).querySelector('path')?.getAttribute('d');
  }

  beforeEach(async () => {
    await TestBed.configureTestingModule({ imports: [Sparkline] }).compileComponents();
    fixture = TestBed.createComponent(Sparkline);
    fixture.componentRef.setInput('description', 'Tendance');
  });

  it('trace un segment continu', async () => {
    expect(await pathFor([1, 2, 3])).toBe('M0.0 22.0 L50.0 12.0 L100.0 2.0');
  });

  it('coupe le tracé sur les valeurs nulles', async () => {
    expect(await pathFor([1, null, 3])).toBe('M0.0 22.0 M100.0 2.0');
  });

  it('ne trace rien sans aucune mesure', async () => {
    expect(await pathFor([null, null])).toBe('');
  });
});
