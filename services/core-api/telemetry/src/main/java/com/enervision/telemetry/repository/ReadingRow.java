package com.enervision.telemetry.repository;

import org.jspecify.annotations.Nullable;

import java.time.Instant;
import java.util.List;

/** One row of {@code readings_raws}. */
public record ReadingRow(
		String siteId,
		Instant ts,
		String source,
		@Nullable Double consumptionKw,
		@Nullable Double consumptionKwImputed,
		@Nullable String imputationMethod,
		@Nullable Double voltageV,
		@Nullable Double currentA,
		@Nullable Double powerFactor,
		@Nullable Double temperatureCelsius,
		@Nullable Double humidityPercent,
		List<String> nullReasons,
		String dataQuality) {
}
