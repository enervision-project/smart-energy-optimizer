package com.enervision.configuration.api.dto;

public record SiteSummaryResponse(
		String siteId,
		String siteName,
		String siteType,
		String location,
		double capacityKw,
		String status) {
}
