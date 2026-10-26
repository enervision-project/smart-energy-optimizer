import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { API_BASE_URL } from './api';
import { HttpEnergyApi } from './http-energy-api';

describe('HttpEnergyApi (mesures)', () => {
  let api: HttpEnergyApi;
  let http: HttpTestingController;
  const from = new Date('2026-10-26T08:00:00Z');
  const to = new Date('2026-10-26T10:00:00Z');

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting(), HttpEnergyApi],
    });
    api = TestBed.inject(HttpEnergyApi);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    http.verify();
  });

  it('appelle GET /api/v1/sites pour récupérer la liste des sites', () => {
    api.getSites().subscribe();
    const req = http.expectOne(`${API_BASE_URL}/sites`);
    expect(req.request.method).toBe('GET');
    req.flush([]);
  });

  it('demande la courbe d’un site avec la période et le pas', () => {
    api.getReadingSeries('SITE001', from, to, '15m').subscribe();
    const req = http.expectOne((r) => r.url === '/api/v1/sites/SITE001/readings');
    expect(req.request.params.get('from')).toBe('2026-10-26T08:00:00.000Z');
    expect(req.request.params.get('to')).toBe('2026-10-26T10:00:00.000Z');
    expect(req.request.params.get('step')).toBe('15m');
    req.flush({ siteId: 'SITE001', step: '15m', from: '', to: '', points: [] });
  });

  it('renvoie null quand le site n’a encore aucune mesure (204)', () => {
    let result: unknown = 'non reçu';
    api.getLatestReading('SITE001').subscribe((r) => (result = r));
    http.expectOne('/api/v1/sites/SITE001/readings/latest').flush(null, {
      status: 204,
      statusText: 'No Content',
    });
    expect(result).toBeNull();
  });

  it('demande la synthèse d’un site sur la période', () => {
    api.getReadingSummary('SITE001', from, to).subscribe();
    const req = http.expectOne((r) => r.url === '/api/v1/sites/SITE001/readings/summary');
    expect(req.request.params.get('from')).toBe('2026-10-26T08:00:00.000Z');
    req.flush({});
  });
});
