package com.enervision.diagnostic.entity;

import java.util.Arrays;

/**
 * Alert severities sent by the energy API, from the least to the most severe.
 */
public enum AlertSeverity {

	LOW("low"),
	MEDIUM("medium"),
	HIGH("high"),
	CRITICAL("critical");

	private final String code;

	AlertSeverity(String code) {
		this.code = code;
	}

	/** Value stored in the database and exposed by the API. */
	public String code() {
		return code;
	}

	public static AlertSeverity fromCode(String code) {
		return Arrays.stream(values())
			.filter(severity -> severity.code.equalsIgnoreCase(code.trim()))
			.findFirst()
			.orElseThrow(() -> new IllegalArgumentException("Unknown alert severity: " + code));
	}

}
