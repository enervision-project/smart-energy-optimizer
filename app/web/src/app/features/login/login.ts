import { HttpErrorResponse } from '@angular/common/http';
import { Component, inject, input, signal } from '@angular/core';
import { FormControl, FormGroup, ReactiveFormsModule, Validators } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';
import { Auth } from '../../core/services/auth';

@Component({
  imports: [ReactiveFormsModule, RouterLink],
  selector: 'app-login',
  styleUrl: './login.scss',
  templateUrl: './login.html',
})
export class Login {
  private readonly auth = inject(Auth);
  private readonly router = inject(Router);

  protected readonly enabled = this.auth.enabled;

  readonly returnUrl = input<string>();

  protected readonly form = new FormGroup({
    email: new FormControl('', {
      nonNullable: true,
      validators: [Validators.required, Validators.email],
    }),
    password: new FormControl('', { nonNullable: true, validators: [Validators.required] }),
  });

  protected readonly pending = signal(false);
  protected readonly error = signal<string | undefined>(undefined);

  protected submit(): void {
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }
    this.pending.set(true);
    this.error.set(undefined);
    const { email, password } = this.form.getRawValue();
    this.auth.login(email, password).subscribe({
      next: () => void this.router.navigateByUrl(this.target()),
      error: (error: unknown) => {
        this.pending.set(false);
        this.error.set(
          error instanceof HttpErrorResponse && error.status === 401
            ? 'Email ou mot de passe incorrect.'
            : 'Connexion impossible : API injoignable, réessayez dans un instant.',
        );
      },
    });
  }

  /** Application pages only, no external URL. */
  private target(): string {
    const url = this.returnUrl();
    return url?.startsWith('/') && !url.startsWith('//') && !url.startsWith('/login')
      ? url
      : '/parc';
  }
}
