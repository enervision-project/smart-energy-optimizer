package com.enervision.telemetry.service;

import com.enervision.common.security.CurrentUser;
import com.enervision.telemetry.api.dto.PredictionSeriesResponse;
import org.jspecify.annotations.Nullable;

import java.time.Instant;

/** Hourly forecasts for a visible site; missing or inaccessible sites are reported as not found. */
public interface PredictionService {

	/**
	 * Aligns from down and to up to UTC hours. Without bounds, returns 24 hours starting at the current hour.
	 * With only one bound, the other is 24 hours away from its aligned value. Periods are capped at 366 days.
	 */
	PredictionSeriesResponse getPredictions(CurrentUser user, String siteId, @Nullable Instant from,
			@Nullable Instant to);

}
