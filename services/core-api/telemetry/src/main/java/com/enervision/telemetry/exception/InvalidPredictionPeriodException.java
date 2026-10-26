package com.enervision.telemetry.exception;

import java.time.Duration;
import java.time.Instant;

public class InvalidPredictionPeriodException extends RuntimeException {

	private InvalidPredictionPeriodException(String message) {
		super(message);
	}

	public static InvalidPredictionPeriodException empty(Instant from, Instant to) {
		return new InvalidPredictionPeriodException(
				"Invalid period: from (" + from + ") must be before to (" + to + ")");
	}

	public static InvalidPredictionPeriodException tooLong(Instant from, Instant to, Duration max) {
		return new InvalidPredictionPeriodException(
				"Invalid period: " + from + " to " + to + " exceeds the maximum of " + max.toDays() + " days");
	}

}
