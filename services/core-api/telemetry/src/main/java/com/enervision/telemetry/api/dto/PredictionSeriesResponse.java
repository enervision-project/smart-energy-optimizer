package com.enervision.telemetry.api.dto;

import java.time.Instant;
import java.util.List;

/** Forecasts over [from, to), one point per UTC hour, oldest first, missing hours included. */
public record PredictionSeriesResponse(
		String siteId,
		String step,
		Instant from,
		Instant to,
		List<PredictionPointResponse> points) {
}
