import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { ApplicationConfig, provideBrowserGlobalErrorListeners } from '@angular/core';
import { provideRouter, withComponentInputBinding } from '@angular/router';
import { provideCharts, withDefaultRegisterables } from 'ng2-charts';
import { environment } from '../environments/environment';
import { routes } from './app.routes';
import { authInterceptor } from './core/interceptors/auth-interceptor';
import { EnergyApi } from './core/services/energy-api';
import { HttpEnergyApi } from './core/services/http-energy-api';
import { MockEnergyApi } from './core/services/mock-energy-api';

export const appConfig: ApplicationConfig = {
  providers: [
    provideBrowserGlobalErrorListeners(),
    provideRouter(routes, withComponentInputBinding()),
    provideHttpClient(withInterceptors([authInterceptor])),
    provideCharts(withDefaultRegisterables()),
    { provide: EnergyApi, useClass: environment.useMock ? MockEnergyApi : HttpEnergyApi },
  ],
};
