package com.enervision.user.security;

import org.jspecify.annotations.Nullable;
import org.springframework.boot.context.properties.ConfigurationProperties;

/**
 * First administrator account ({@code enervision.security.initial-admin.*}), created at startup when the users
 * table is empty (see {@link InitialAdminInitializer}). No email: nothing is created.
 *
 * @param email    login of the administrator
 * @param password plain-text password, hashed before being stored
 */
@ConfigurationProperties("enervision.security.initial-admin")
public record InitialAdminProperties(
		@Nullable String email,
		@Nullable String password) {
}
