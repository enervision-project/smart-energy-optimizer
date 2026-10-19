import { ComponentFixture, TestBed } from '@angular/core/testing';
import { Parc } from './parc';

describe('Parc', () => {
  let component: Parc;
  let fixture: ComponentFixture<Parc>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [Parc],
    }).compileComponents();

    fixture = TestBed.createComponent(Parc);
    component = fixture.componentInstance;
    await fixture.whenStable();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});
