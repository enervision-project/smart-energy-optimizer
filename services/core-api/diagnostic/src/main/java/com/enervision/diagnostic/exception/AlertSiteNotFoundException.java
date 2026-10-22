package com.enervision.diagnostic.exception;

/**
 * Alerts requested for a site that does not exist or that the user cannot see.
 */
public class AlertSiteNotFoundException extends RuntimeException {

	public AlertSiteNotFoundException(String siteId) {
		super("Site " + siteId + " not found");
	}

}
