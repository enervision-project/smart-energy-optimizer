package com.enervision.telemetry.api.dto;

import org.jspecify.annotations.Nullable;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;

/** {@code predictionKwh} is energy over the UTC hour starting at {@code ts}, not instantaneous power. */
public record PredictionPointResponse(
		Instant ts,
		@Nullable BigDecimal predictionKwh,
		@Nullable UUID runId,
		@Nullable String modelName,
		@Nullable String modelVersion,
		@Nullable Instant generatedAt) {
}
