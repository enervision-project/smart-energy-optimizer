import { ComponentFixture, TestBed } from '@angular/core/testing';
import { AlertBanner } from './alert-banner';

describe('AlertBanner', () => {
  let component: AlertBanner;
  let fixture: ComponentFixture<AlertBanner>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [AlertBanner],
    }).compileComponents();

    fixture = TestBed.createComponent(AlertBanner);
    component = fixture.componentInstance;
    await fixture.whenStable();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});
