package com.enervision.telemetry.api.dto;

import org.jspecify.annotations.Nullable;

import java.time.Instant;
import java.util.List;

/**
 * Last reading stored for a site.
 *
 * @param ts                   minute of the reading (UTC)
 * @param ageSeconds           seconds since {@code ts}: a large value means the collection has stopped
 * @param source               {@code current} (real time), {@code readings} or {@code backfill} (history)
 * @param consumptionKw        raw value, {@code null} when the sensor failed
 * @param consumptionKwImputed estimated value when the raw one is {@code null}
 * @param imputationMethod     {@code previous_value} or {@code linear}, with {@code consumptionKwImputed}
 */
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
