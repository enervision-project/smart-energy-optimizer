import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { App } from './app';

describe('App', () => {
  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [App],
      providers: [provideRouter([])],
    }).compileComponents();
  });

  it('should create the app', () => {
    const fixture = TestBed.createComponent(App);
    expect(fixture.componentInstance).toBeTruthy();
  });

  it('should render brand', async () => {
    const fixture = TestBed.createComponent(App);
    await fixture.whenStable();
    const compiled = fixture.nativeElement as HTMLElement;
    const logo = compiled.querySelector('img.brand');
    expect(logo?.getAttribute('alt')).toBe('EnerVision');
    expect(logo?.getAttribute('src')).toBe('asset/logo_long.png');
  });

  it('propose une entrée Sites dans le menu latéral', async () => {
    const fixture = TestBed.createComponent(App);
    await fixture.whenStable();
    const links = [...(fixture.nativeElement as HTMLElement).querySelectorAll('.sidebar a')];
    const sites = links.find((a) => a.textContent?.trim() === 'Sites');
    expect(sites?.getAttribute('href')).toBe('/sites');
  });
});
