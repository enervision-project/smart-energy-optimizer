package com.enervision.diagnostic.api.handler;

import com.enervision.configuration.exception.SiteNotFoundException;
import com.enervision.diagnostic.exception.AlertSiteNotFoundException;
import com.enervision.diagnostic.exception.InvalidAlertPeriodException;
import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

/**
 * Maps the diagnostic module's exceptions to ProblemDetail responses.
 * Scoped to this module's controllers so it does not interfere with other modules.
 */
@RestControllerAdvice(basePackages = "com.enervision.diagnostic")
class DiagnosticExceptionHandler {

	@ExceptionHandler({AlertSiteNotFoundException.class, SiteNotFoundException.class})
	ProblemDetail handleSiteNotFound(RuntimeException exception) {
		return ProblemDetail.forStatusAndDetail(HttpStatus.NOT_FOUND, exception.getMessage());
	}

	@ExceptionHandler(InvalidAlertPeriodException.class)
	ProblemDetail handleInvalidPeriod(InvalidAlertPeriodException exception) {
		return ProblemDetail.forStatusAndDetail(HttpStatus.BAD_REQUEST, exception.getMessage());
	}

}
