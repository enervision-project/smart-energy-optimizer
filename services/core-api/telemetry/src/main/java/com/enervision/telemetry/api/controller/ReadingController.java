package com.enervision.telemetry.api.controller;

import com.enervision.common.security.CurrentUser;
import com.enervision.telemetry.api.dto.LatestReadingResponse;
import com.enervision.telemetry.api.dto.ReadingSeriesResponse;
import com.enervision.telemetry.api.dto.ReadingStep;
import com.enervision.telemetry.api.dto.ReadingSummaryResponse;
import com.enervision.telemetry.service.ReadingService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import lombok.RequiredArgsConstructor;
import org.jspecify.annotations.Nullable;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.time.Instant;

@RestController
@RequestMapping("/api/v1/sites/{siteId}/readings")
@RequiredArgsConstructor
@Tag(name = "Readings")
public class ReadingController {

	private final ReadingService readingService;

	@GetMapping
	@Operation(summary = "Readings of a site, one point per step (1m, 15m or 1h), last 48 hours by default")
	public ReadingSeriesResponse getReadings(
			CurrentUser currentUser,
			@PathVariable String siteId,
			@RequestParam(required = false) @Nullable Instant from,
			@RequestParam(required = false) @Nullable Instant to,
			@RequestParam(defaultValue = "15m") ReadingStep step) {
		return readingService.getReadings(currentUser, siteId, from, to, step);
	}

	@GetMapping("/latest")
	@Operation(summary = "Last reading of a site (204 when it has none)")
	public ResponseEntity<LatestReadingResponse> getLatest(CurrentUser currentUser, @PathVariable String siteId) {
		return readingService.getLatest(currentUser, siteId)
			.map(ResponseEntity::ok)
			.orElseGet(() -> ResponseEntity.noContent().build());
	}

	@GetMapping("/summary")
	@Operation(summary = "Energy, peak and availability of a site, last 48 hours by default")
	public ReadingSummaryResponse getSummary(
			CurrentUser currentUser,
			@PathVariable String siteId,
			@RequestParam(required = false) @Nullable Instant from,
			@RequestParam(required = false) @Nullable Instant to) {
		return readingService.getSummary(currentUser, siteId, from, to);
	}

}
