package com.enervision.telemetry.api.handler;

import com.enervision.telemetry.exception.InvalidPredictionPeriodException;
import com.enervision.telemetry.exception.InvalidReadingPeriodException;
import com.enervision.telemetry.exception.TelemetrySiteNotFoundException;
import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

/**
 * Maps the telemetry module's exceptions to ProblemDetail responses.
 * Scoped to this module's controllers so it does not interfere with other modules.
 */
@RestControllerAdvice(basePackages = "com.enervision.telemetry")
class TelemetryExceptionHandler {

	@ExceptionHandler(TelemetrySiteNotFoundException.class)
	ProblemDetail handleSiteNotFound(TelemetrySiteNotFoundException exception) {
		return ProblemDetail.forStatusAndDetail(HttpStatus.NOT_FOUND, exception.getMessage());
	}

	@ExceptionHandler(InvalidPredictionPeriodException.class)
	ProblemDetail handleInvalidPredictionPeriod(InvalidPredictionPeriodException exception) {
		return ProblemDetail.forStatusAndDetail(HttpStatus.BAD_REQUEST, exception.getMessage());
	}

	@ExceptionHandler(InvalidReadingPeriodException.class)
	ProblemDetail handleInvalidPeriod(InvalidReadingPeriodException exception) {
		return ProblemDetail.forStatusAndDetail(HttpStatus.BAD_REQUEST, exception.getMessage());
	}

}
