package com.enervision.diagnostic.api.dto;

import org.jspecify.annotations.Nullable;

import java.time.Instant;

public record AlertResponse(
		String alertId,
		String siteId,
		String siteName,
		Instant timestamp,
		String severity,
		String type,
		String message,
		@Nullable Double value,
		double threshold,
		boolean recent) {
}
