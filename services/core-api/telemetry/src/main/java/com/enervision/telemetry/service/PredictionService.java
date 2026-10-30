package com.enervision.telemetry.service;

import com.enervision.common.security.CurrentUser;
import com.enervision.telemetry.api.dto.PredictionSeriesResponse;
import org.jspecify.annotations.Nullable;

import java.time.Instant;

/** Hourly forecasts for a visible site; missing or inaccessible sites are reported as not found. */
public interface PredictionService {

	/** Aligns bounds to UTC hours; defaults to the next 24 hours, periods are capped at 366 days. */
	PredictionSeriesResponse getPredictions(CurrentUser user, String siteId, @Nullable Instant from,
			@Nullable Instant to);

}
