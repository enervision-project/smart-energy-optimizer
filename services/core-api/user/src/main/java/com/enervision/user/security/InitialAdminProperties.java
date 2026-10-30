package com.enervision.user.security;

import org.jspecify.annotations.Nullable;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties("enervision.security.initial-admin")
public record InitialAdminProperties(
		@Nullable String email,
		@Nullable String password) {
}
