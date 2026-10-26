package com.enervision.telemetry.api.dto;

import java.time.Instant;
import java.util.List;

/**
 * Readings of a site over {@code [from, to)}, one point per step, oldest first.
 *
 * @param step {@code 1m}, {@code 15m} or {@code 1h}
 * @param from start of the first step
 * @param to   end of the last step, excluded
 */
public record ReadingSeriesResponse(
		String siteId,
		String step,
		Instant from,
		Instant to,
		List<ReadingPoint> points) {
}
