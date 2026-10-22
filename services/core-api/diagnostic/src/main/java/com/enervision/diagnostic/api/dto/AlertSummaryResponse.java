package com.enervision.diagnostic.api.dto;

import java.time.Instant;
import java.util.Map;

/**
 * Recent alerts count.
 *
 * @param since      start of the counted period (an hour before the request)
 * @param total      every alert of the period, including those with an unknown severity
 * @param bySeverity count per known severity code, from {@code low} to {@code critical}, zero included
 */
public record AlertSummaryResponse(
		Instant since,
		long total,
		Map<String, Long> bySeverity) {
}
