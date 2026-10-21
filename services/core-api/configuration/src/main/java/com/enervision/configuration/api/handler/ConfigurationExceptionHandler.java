package com.enervision.configuration.api.handler;

import com.enervision.configuration.exception.SiteNotFoundException;
import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

/**
 * Maps the configuration module's exceptions to ProblemDetail responses.
 * Scoped to this module's controllers so it does not interfere with other modules.
 */
@RestControllerAdvice(basePackages = "com.enervision.configuration")
class ConfigurationExceptionHandler {

	@ExceptionHandler(SiteNotFoundException.class)
	ProblemDetail handleSiteNotFound(SiteNotFoundException exception) {
		return ProblemDetail.forStatusAndDetail(HttpStatus.NOT_FOUND, exception.getMessage());
	}

}
