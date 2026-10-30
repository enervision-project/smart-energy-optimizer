package com.enervision.user.security;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

import java.time.Duration;

@Validated
@ConfigurationProperties("enervision.security.jwt")
public record JwtProperties(
		@NotBlank String secret,
		@NotNull Duration expiration,
		@NotBlank String issuer) {
}
