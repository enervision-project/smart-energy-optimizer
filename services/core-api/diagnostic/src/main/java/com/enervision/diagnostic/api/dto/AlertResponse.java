package com.enervision.diagnostic.api.dto;

import org.jspecify.annotations.Nullable;

import java.time.Instant;

/**
 * @param severity raw value sent by the energy API ({@code low}, {@code medium}, {@code high}, {@code critical})
 * @param type     raw value sent by the energy API ({@code spike}, {@code threshold}, {@code anomaly},
 *                 {@code outage}, {@code sensor})
 * @param value    measured value, {@code null} when the API did not send one
 * @param recent   {@code true} when the alert is less than an hour old
 */
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
