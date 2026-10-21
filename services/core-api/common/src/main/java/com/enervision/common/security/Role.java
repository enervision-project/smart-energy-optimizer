package com.enervision.common.security;

/**
 * Application roles, exposed to Spring Security as {@code ROLE_USER} / {@code ROLE_ADMIN}.
 */
public enum Role {
	USER,
	ADMIN;

	/** Prefix Spring Security expects on role authorities (used by {@code hasRole(...)}). */
	public static final String AUTHORITY_PREFIX = "ROLE_";

	/** Spring Security authority of this role, e.g. {@code ROLE_ADMIN}. */
	public String authority() {
		return AUTHORITY_PREFIX + name();
	}

}
