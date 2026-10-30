package com.enervision.telemetry.exception;

public class TelemetrySiteNotFoundException extends RuntimeException {

	public TelemetrySiteNotFoundException(String siteId) {
		super("Site " + siteId + " not found");
	}

}
