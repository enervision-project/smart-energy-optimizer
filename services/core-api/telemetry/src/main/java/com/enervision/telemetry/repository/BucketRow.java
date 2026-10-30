package com.enervision.telemetry.repository;

import org.jspecify.annotations.Nullable;

import java.time.Instant;
import java.util.List;

public record BucketRow(
		Instant bucket,
		@Nullable Double consumptionKw,
		@Nullable Double consumptionKwImputed,
		@Nullable Double voltageV,
		@Nullable Double currentA,
		@Nullable Double powerFactor,
		@Nullable Double temperatureCelsius,
		@Nullable Double humidityPercent,
		int worstQuality,
		int minutesReceived,
		int minutesBackfilled,
		int minutesImputed,
		List<String> imputationMethods,
		List<String> nullReasons) {
}
