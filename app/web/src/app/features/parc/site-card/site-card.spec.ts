import { ComponentFixture, TestBed } from '@angular/core/testing';
import { SiteCard } from './site-card';

describe('SiteCard', () => {
  let component: SiteCard;
  let fixture: ComponentFixture<SiteCard>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [SiteCard],
    }).compileComponents();

    fixture = TestBed.createComponent(SiteCard);
    component = fixture.componentInstance;
    await fixture.whenStable();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});
