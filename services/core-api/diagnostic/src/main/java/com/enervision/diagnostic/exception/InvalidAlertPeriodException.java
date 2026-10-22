package com.enervision.diagnostic.exception;

import java.time.Instant;

public class InvalidAlertPeriodException extends RuntimeException {

	public InvalidAlertPeriodException(Instant from, Instant to) {
		super("Invalid period: from (" + from + ") is after to (" + to + ")");
	}

}
