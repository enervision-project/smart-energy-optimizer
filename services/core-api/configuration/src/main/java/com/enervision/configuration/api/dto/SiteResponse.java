package com.enervision.configuration.api.dto;

import org.jspecify.annotations.Nullable;

import java.time.Instant;

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
