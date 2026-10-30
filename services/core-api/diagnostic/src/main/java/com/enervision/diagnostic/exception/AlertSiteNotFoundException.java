package com.enervision.diagnostic.exception;

public class AlertSiteNotFoundException extends RuntimeException {

	public AlertSiteNotFoundException(String siteId) {
		super("Site " + siteId + " not found");
	}

}
