package com.enervision.telemetry.api.controller;

import com.enervision.common.security.CurrentUser;
import com.enervision.telemetry.api.dto.ParkSummaryResponse;
import com.enervision.telemetry.service.ParkService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/v1/stats")
@RequiredArgsConstructor
@Tag(name = "Stats")
public class StatsController {

	private final ParkService parkService;

	@GetMapping("/summary")
	@Operation(summary = "Current consumption of the visible sites, with the sites lacking recent data")
	public ParkSummaryResponse getSummary(CurrentUser currentUser) {
		return parkService.getSummary(currentUser);
	}

}
