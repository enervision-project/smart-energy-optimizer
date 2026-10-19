import { ComponentFixture, TestBed } from '@angular/core/testing';
import { Previsions } from './previsions';

describe('Previsions', () => {
  let component: Previsions;
  let fixture: ComponentFixture<Previsions>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [Previsions],
    }).compileComponents();

    fixture = TestBed.createComponent(Previsions);
    component = fixture.componentInstance;
    await fixture.whenStable();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});
