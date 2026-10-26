package com.enervision.telemetry.api.dto;

import org.jspecify.annotations.Nullable;

import java.time.Instant;

/**
 * Current consumption of a site.
 *
 * @param currentConsumptionKw raw value of the last reading, or its imputed value when the sensor failed;
 *                             {@code null} without a recent reading or without any value
 * @param consumptionImputed   {@code true} when {@code currentConsumptionKw} is an estimate
 * @param loadPercent          {@code currentConsumptionKw / capacityKw}
 * @param dataQuality          quality of the last reading; {@code null} without a recent reading
 * @param ts                   minute of the last recent reading
 * @param ageSeconds           seconds since {@code ts}
 */
public record SiteLoadResponse(
		String siteId,
		String siteName,
		@Nullable Double currentConsumptionKw,
		boolean consumptionImputed,
		double capacityKw,
		@Nullable Double loadPercent,
		@Nullable String dataQuality,
		@Nullable Instant ts,
		@Nullable Long ageSeconds) {
}
