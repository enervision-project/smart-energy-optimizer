package com.enervision.telemetry.api.dto;

import java.time.Instant;
import java.util.List;

public record ReadingSeriesResponse(
		String siteId,
		String step,
		Instant from,
		Instant to,
		List<ReadingPoint> points) {
}
