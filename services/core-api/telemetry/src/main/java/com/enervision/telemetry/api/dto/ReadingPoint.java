package com.enervision.telemetry.api.dto;

import org.jspecify.annotations.Nullable;

import java.time.Instant;
import java.util.List;

/** A step without readings is still returned, with {@code null} values, so that the chart shows the gap. */
public record ReadingPoint(
		Instant ts,
		@Nullable Double consumptionKw,
		@Nullable Double consumptionKwImputed,
		@Nullable Double voltageV,
		@Nullable Double currentA,
		@Nullable Double powerFactor,
		@Nullable Double temperatureCelsius,
		@Nullable Double humidityPercent,
		@Nullable String dataQuality,
		List<String> nullReasons,
		int minutesExpected,
		int minutesReceived,
		int minutesBackfilled,
		int minutesImputed,
		List<String> imputationMethods) {
}
