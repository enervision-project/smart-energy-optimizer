package com.enervision.user.security;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

import java.time.Duration;

/**
 * JWT configuration ({@code enervision.security.jwt.*}).
 *
 * @param secret     Base64-encoded HMAC-SHA256 key, at least 32 bytes
 * @param expiration token lifetime
 * @param issuer     issuer written to the {@code iss} claim and checked on decoding
 */
@Validated
@ConfigurationProperties("enervision.security.jwt")
public record JwtProperties(
		@NotBlank String secret,
		@NotNull Duration expiration,
		@NotBlank String issuer) {
}
