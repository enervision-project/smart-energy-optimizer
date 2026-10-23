package com.enervision.diagnostic.api.controller;

import com.enervision.common.security.CurrentUser;
import com.enervision.diagnostic.api.dto.AlertResponse;
import com.enervision.diagnostic.api.dto.AlertSearchRequest;
import com.enervision.diagnostic.api.dto.AlertSummaryResponse;
import com.enervision.diagnostic.service.AlertService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.PositiveOrZero;
import lombok.RequiredArgsConstructor;
import org.jspecify.annotations.Nullable;
import org.springdoc.core.annotations.ParameterObject;
import org.springframework.data.web.PagedModel;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/v1/alerts")
@RequiredArgsConstructor
@Tag(name = "Alerts")
public class AlertController {

	private static final int MAX_PAGE_SIZE = 200;

	private final AlertService alertService;

	@GetMapping
	@Operation(summary = "List the alerts of the visible sites, newest first (last hour by default)")
	public PagedModel<AlertResponse> getAlerts(
			CurrentUser currentUser,
			@ParameterObject AlertSearchRequest request,
			@RequestParam(defaultValue = "0") @PositiveOrZero int page,
			@RequestParam(defaultValue = "50") @Min(1) @Max(MAX_PAGE_SIZE) int size) {
		return new PagedModel<>(alertService.getAlerts(currentUser, request, page, size));
	}

	@GetMapping("/summary")
	@Operation(summary = "Count the alerts of the last hour per severity")
	public AlertSummaryResponse getSummary(CurrentUser currentUser,
			@RequestParam(required = false) @Nullable String siteId) {
		return alertService.getSummary(currentUser, siteId);
	}

}
