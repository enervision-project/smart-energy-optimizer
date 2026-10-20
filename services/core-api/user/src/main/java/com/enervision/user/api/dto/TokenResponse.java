package com.enervision.user.api.dto;

/**
 * JWT access token, to be sent in the {@code Authorization: Bearer <accessToken>} header.
 *
 * @param expiresIn lifetime in seconds
 */
public record TokenResponse(
		String accessToken,
		String tokenType,
		long expiresIn) {
}
