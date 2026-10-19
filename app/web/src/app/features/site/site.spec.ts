import { ComponentFixture, TestBed } from '@angular/core/testing';
import { Site } from './site';

describe('Site', () => {
  let component: Site;
  let fixture: ComponentFixture<Site>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [Site],
    }).compileComponents();

    fixture = TestBed.createComponent(Site);
    component = fixture.componentInstance;
    await fixture.whenStable();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});
