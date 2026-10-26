package com.enervision.telemetry.exception;

/**
 * Readings requested for a site that does not exist or that the user cannot see.
 */
public class TelemetrySiteNotFoundException extends RuntimeException {

	public TelemetrySiteNotFoundException(String siteId) {
		super("Site " + siteId + " not found");
	}

}
