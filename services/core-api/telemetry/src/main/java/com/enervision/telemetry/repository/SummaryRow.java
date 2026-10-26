package com.enervision.telemetry.repository;

import org.jspecify.annotations.Nullable;

import java.time.Instant;

/** Raw-value figures of a site over a period. */
public record SummaryRow(
		@Nullable Double energyKwh,
		int hoursWithData,
		@Nullable Double peakKw,
		@Nullable Instant peakAt,
		int minutesReceived,
		int minutesWithConsumption,
		int minutesImputed) {
}
