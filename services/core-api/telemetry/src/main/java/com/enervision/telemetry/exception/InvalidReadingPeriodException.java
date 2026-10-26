package com.enervision.telemetry.exception;

import java.time.Duration;
import java.time.Instant;

public class InvalidReadingPeriodException extends RuntimeException {

	private InvalidReadingPeriodException(String message) {
		super(message);
	}

	public static InvalidReadingPeriodException empty(Instant from, Instant to) {
		return new InvalidReadingPeriodException(
				"Invalid period: from (" + from + ") must be before to (" + to + ")");
	}

	public static InvalidReadingPeriodException tooLong(Instant from, Instant to, Duration max) {
		return new InvalidReadingPeriodException(
				"Invalid period: " + from + " to " + to + " exceeds the maximum of "
						+ (max.toHours() <= 48 ? max.toHours() + " hours" : max.toDays() + " days"));
	}

}
