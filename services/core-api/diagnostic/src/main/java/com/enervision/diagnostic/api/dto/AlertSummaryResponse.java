package com.enervision.diagnostic.api.dto;

import java.time.Instant;
import java.util.Map;

public record AlertSummaryResponse(
		Instant since,
		long total,
		Map<String, Long> bySeverity) {
}
