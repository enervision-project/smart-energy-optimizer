package com.enervision.diagnostic.entity;

import java.util.Arrays;

public enum AlertSeverity {

	LOW("low"),
	MEDIUM("medium"),
	HIGH("high"),
	CRITICAL("critical");

	private final String code;

	AlertSeverity(String code) {
		this.code = code;
	}

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
