package com.enervision.user.api.dto;

public record TokenResponse(
		String accessToken,
		String tokenType,
		long expiresIn) {
}
