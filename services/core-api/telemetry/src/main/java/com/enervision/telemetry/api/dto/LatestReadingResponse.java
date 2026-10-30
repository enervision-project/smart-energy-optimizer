package com.enervision.telemetry.api.dto;

import org.jspecify.annotations.Nullable;

import java.time.Instant;
import java.util.List;

public record LatestReadingResponse(
		String siteId,
		Instant ts,
		long ageSeconds,
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
