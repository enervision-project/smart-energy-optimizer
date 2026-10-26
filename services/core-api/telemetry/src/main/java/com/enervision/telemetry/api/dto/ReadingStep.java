package com.enervision.telemetry.api.dto;

import java.time.Duration;
import java.util.Arrays;

/**
 * Width of the points of a reading series. Each step caps the requested period so that a series stays small.
 */
public enum ReadingStep {

	ONE_MINUTE("1m", Duration.ofMinutes(1), Duration.ofHours(48)),
	FIFTEEN_MINUTES("15m", Duration.ofMinutes(15), Duration.ofDays(31)),
	ONE_HOUR("1h", Duration.ofHours(1), Duration.ofDays(366));

	private final String code;
	private final Duration duration;
	private final Duration maxPeriod;

	ReadingStep(String code, Duration duration, Duration maxPeriod) {
		this.code = code;
		this.duration = duration;
		this.maxPeriod = maxPeriod;
	}

	/** Value of the query string and of the response ({@code 1m}, {@code 15m}, {@code 1h}). */
	public String code() {
		return code;
	}

	public Duration duration() {
		return duration;
	}

	public Duration maxPeriod() {
		return maxPeriod;
	}

	public static ReadingStep fromCode(String code) {
		return Arrays.stream(values())
			.filter(step -> step.code.equalsIgnoreCase(code.trim()))
			.findFirst()
			.orElseThrow(() -> new IllegalArgumentException("Unknown reading step: " + code));
	}

}
