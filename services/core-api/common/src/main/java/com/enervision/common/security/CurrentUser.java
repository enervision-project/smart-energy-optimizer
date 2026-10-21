package com.enervision.common.security;

import java.util.UUID;

/**
 * Authenticated user of the current request. Declare it as a controller method parameter to have it injected
 * (see {@link CurrentUserArgumentResolver}), then pass it to the service.
 */
public record CurrentUser(UUID id, Role role) {

	public boolean isAdmin() {
		return role == Role.ADMIN;
	}

}
