package com.enervision.telemetry.api.dto;

import org.jspecify.annotations.Nullable;

import java.time.Instant;
import java.util.List;

/**
 * Current consumption of the visible sites, as the energy API's {@code /stats/summary}, computed from the database.
 *
 * @param totalConsumptionKw sum over the sites with a value; the others are left out
 * @param totalCapacityKw    capacity of every visible site
 * @param averageLoadPercent {@code totalConsumptionKw / totalCapacityKw}
 * @param sitesWithoutData   sites without a recent value: the dashboard must warn that the totals are incomplete
 */
public record ParkSummaryResponse(
		Instant timestamp,
		int totalSites,
		double totalConsumptionKw,
		double totalCapacityKw,
		@Nullable Double averageLoadPercent,
		List<String> sitesWithoutData,
		List<SiteLoadResponse> sites) {
}
