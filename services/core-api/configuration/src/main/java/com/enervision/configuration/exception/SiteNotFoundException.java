package com.enervision.configuration.exception;

public class SiteNotFoundException extends RuntimeException {

	public SiteNotFoundException(String siteId) {
		super("Site " + siteId + " not found");
	}

}
