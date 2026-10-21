package com.enervision.configuration.api.dto;

import org.jspecify.annotations.Nullable;

import java.time.Instant;

/**
 * @param profile reference profile, {@code null} when none has been loaded for this site
 */
public record SiteResponse(
		String siteId,
		String siteName,
		String siteType,
		String location,
		double capacityKw,
		String status,
		Instant updatedAt,
		@Nullable SiteProfileResponse profile) {
}
