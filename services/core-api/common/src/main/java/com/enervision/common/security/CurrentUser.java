package com.enervision.common.security;

import java.util.UUID;

/** Authenticated user of the request, injectable as a controller method parameter. */
public record CurrentUser(UUID id, Role role) {

	public boolean isAdmin() {
		return role == Role.ADMIN;
	}

}
