package com.enervision.telemetry.api.dto;

import org.jspecify.annotations.Nullable;

import java.time.Instant;

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
