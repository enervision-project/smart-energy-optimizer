package com.enervision.telemetry.api.dto;

import org.jspecify.annotations.Nullable;

import java.time.Instant;

/** Computed from raw values only; hours without a value are left out of {@code energyKwh}. */
public record ReadingSummaryResponse(
		String siteId,
		Instant from,
		Instant to,
		@Nullable Double energyKwh,
		int hoursWithData,
		int hoursExpected,
		@Nullable Double peakKw,
		@Nullable Instant peakAt,
		@Nullable Double availabilityPercent,
		int minutesExpected,
		int minutesReceived,
		int minutesWithConsumption,
		int minutesImputed) {
}
