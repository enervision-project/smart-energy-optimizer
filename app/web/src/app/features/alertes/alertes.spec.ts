import { ComponentFixture, TestBed } from '@angular/core/testing';
import { Alertes } from './alertes';

describe('Alertes', () => {
  let component: Alertes;
  let fixture: ComponentFixture<Alertes>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [Alertes],
    }).compileComponents();

    fixture = TestBed.createComponent(Alertes);
    component = fixture.componentInstance;
    await fixture.whenStable();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});
