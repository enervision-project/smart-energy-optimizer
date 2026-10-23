package com.enervision.diagnostic.api.dto;

import java.time.Instant;
import java.util.List;

public record RecommendationResponse(
		String siteId,
		Instant timestamp,
		List<RecommendationItemResponse> items) {
}
