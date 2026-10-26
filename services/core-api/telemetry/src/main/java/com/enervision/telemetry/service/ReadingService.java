package com.enervision.telemetry.service;

import com.enervision.common.security.CurrentUser;
import com.enervision.telemetry.api.dto.LatestReadingResponse;
import com.enervision.telemetry.api.dto.ReadingSeriesResponse;
import com.enervision.telemetry.api.dto.ReadingStep;
import com.enervision.telemetry.api.dto.ReadingSummaryResponse;
import org.jspecify.annotations.Nullable;

import java.time.Instant;
import java.util.Optional;

/**
 * Readings of a site visible to the user (see {@code SiteService}); a site the user cannot see is reported as not
 * found. Without {@code from} and {@code to}, a period covers the last 48 hours.
 */
public interface ReadingService {

	/** One point per step of {@code [from, to)}, aligned on UTC, steps without any reading included. */
	ReadingSeriesResponse getReadings(CurrentUser user, String siteId, @Nullable Instant from,
			@Nullable Instant to, ReadingStep step);

	/** Last reading stored for the site, empty when it has none. */
	Optional<LatestReadingResponse> getLatest(CurrentUser user, String siteId);

	/** Energy, peak and availability over {@code [from, to)}, from raw values only. */
	ReadingSummaryResponse getSummary(CurrentUser user, String siteId, @Nullable Instant from,
			@Nullable Instant to);

}
