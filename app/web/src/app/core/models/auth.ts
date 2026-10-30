export interface TokenResponse {
  accessToken: string;
  tokenType: string;
  /** In seconds. */
  expiresIn: number;
}

export interface User {
  id: string;
  email: string;
  firstName: string;
  lastName: string;
  companyName: string;
  role: 'USER' | 'ADMIN';
}
