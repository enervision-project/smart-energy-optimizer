package com.enervision.telemetry.api.dto;

import org.jspecify.annotations.Nullable;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;

/**
 * One UTC hour, starting at ts. Missing forecasts have a null value and null publication metadata.
 * predictionKwh is energy over that hour, not instantaneous power.
 */
public record PredictionPointResponse(
		Instant ts,
		@Nullable BigDecimal predictionKwh,
		@Nullable UUID runId,
		@Nullable String modelName,
		@Nullable String modelVersion,
		@Nullable Instant generatedAt) {
}
