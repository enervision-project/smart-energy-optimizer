package com.enervision.user.exception;

public class EmailAlreadyUsedException extends RuntimeException {

	public EmailAlreadyUsedException(String email) {
		super("Email address " + email + " is already in use");
	}

}
