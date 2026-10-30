package com.enervision.common.security;

public enum Role {
	USER,
	ADMIN;

	/** Prefix Spring Security expects on role authorities (used by {@code hasRole(...)}). */
	public static final String AUTHORITY_PREFIX = "ROLE_";

	public String authority() {
		return AUTHORITY_PREFIX + name();
	}

}
