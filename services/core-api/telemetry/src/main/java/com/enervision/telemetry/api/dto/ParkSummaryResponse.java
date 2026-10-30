package com.enervision.telemetry.api.dto;

import org.jspecify.annotations.Nullable;

import java.time.Instant;
import java.util.List;

/** Totals skip sites in {@code sitesWithoutData}: the dashboard must warn that they are incomplete. */
public record ParkSummaryResponse(
		Instant timestamp,
		int totalSites,
		double totalConsumptionKw,
		double totalCapacityKw,
		@Nullable Double averageLoadPercent,
		List<String> sitesWithoutData,
		List<SiteLoadResponse> sites) {
}
