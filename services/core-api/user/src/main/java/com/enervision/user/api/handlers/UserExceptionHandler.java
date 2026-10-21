package com.enervision.user.api.handlers;

import com.enervision.user.exception.UserNotFoundException;
import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.security.core.AuthenticationException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

/**
 * Maps the user module's exceptions to ProblemDetail responses.
 * Scoped to this module's controllers so it does not interfere with other modules.
 */
@RestControllerAdvice(basePackages = "com.enervision.user")
class UserExceptionHandler {

	@ExceptionHandler(UserNotFoundException.class)
	ProblemDetail handleUserNotFound(UserNotFoundException exception) {
		return ProblemDetail.forStatusAndDetail(HttpStatus.NOT_FOUND, exception.getMessage());
	}

	/** Login failure: the message is deliberately generic so it does not reveal whether the email exists. */
	@ExceptionHandler(AuthenticationException.class)
	ProblemDetail handleAuthenticationFailure(AuthenticationException exception) {
		return ProblemDetail.forStatusAndDetail(HttpStatus.UNAUTHORIZED, "Invalid credentials");
	}

}
