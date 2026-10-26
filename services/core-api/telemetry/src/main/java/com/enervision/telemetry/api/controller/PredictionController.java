package com.enervision.telemetry.api.controller;

import com.enervision.common.security.CurrentUser;
import com.enervision.telemetry.api.dto.PredictionSeriesResponse;
import com.enervision.telemetry.service.PredictionService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import lombok.RequiredArgsConstructor;
import org.jspecify.annotations.Nullable;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.time.Instant;

@RestController
@RequestMapping("/api/v1/sites/{siteId}/predictions")
@RequiredArgsConstructor
@Tag(name = "Predictions")
public class PredictionController {

	private final PredictionService predictionService;

	@GetMapping
	@Operation(summary = "Latest complete forecast per hour, 24 hours from the current UTC hour by default", description = "UTC bounds are aligned to full hours. End is exclusive. Maximum period: 366 days. "
			+ "Values are hourly energy in kWh; missing forecasts are null.")
	public PredictionSeriesResponse getPredictions(
			CurrentUser currentUser,
			@PathVariable String siteId,
			@RequestParam(required = false) @Nullable Instant from,
			@RequestParam(required = false) @Nullable Instant to) {
		return predictionService.getPredictions(currentUser, siteId, from, to);
	}

}
