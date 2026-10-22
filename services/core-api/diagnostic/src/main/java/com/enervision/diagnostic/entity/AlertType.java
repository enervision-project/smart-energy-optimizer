package com.enervision.diagnostic.entity;

import java.util.Arrays;

/**
 * Alert types sent by the energy API.
 */
public enum AlertType {

	/** Sudden consumption peak. */
	SPIKE("spike"),
	/** Configured threshold exceeded. */
	THRESHOLD("threshold"),
	/** Statistically abnormal behaviour. */
	ANOMALY("anomaly"),
	/** Risk of overload or imminent outage. */
	OUTAGE("outage"),
	/** Sensor failure. */
	SENSOR("sensor");

	private final String code;

	AlertType(String code) {
		this.code = code;
	}

	/** Value stored in the database and exposed by the API. */
	public String code() {
		return code;
	}

	public static AlertType fromCode(String code) {
		return Arrays.stream(values())
			.filter(type -> type.code.equalsIgnoreCase(code.trim()))
			.findFirst()
			.orElseThrow(() -> new IllegalArgumentException("Unknown alert type: " + code));
	}

}
