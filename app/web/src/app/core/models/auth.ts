/** Réponse de POST /api/v1/auth/login. */
export interface TokenResponse {
  accessToken: string;
  tokenType: string;
  /** Durée de validité du jeton, en secondes. */
  expiresIn: number;
}

/** Utilisateur connecté, renvoyé par GET /api/v1/users/me. */
export interface User {
  id: string;
  email: string;
  firstName: string;
  lastName: string;
  companyName: string;
  role: 'USER' | 'ADMIN';
}
