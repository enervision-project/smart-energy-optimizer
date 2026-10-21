package com.enervision.configuration.api.controller;

import com.enervision.common.security.CurrentUser;
import com.enervision.configuration.api.dto.SiteResponse;
import com.enervision.configuration.api.dto.SiteSummaryResponse;
import com.enervision.configuration.service.SiteService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

@RestController
@RequestMapping("/api/v1/sites")
@RequiredArgsConstructor
@Tag(name = "Sites")
public class SiteController {

	private final SiteService siteService;

	@GetMapping
	@Operation(summary = "List the sites visible to the current user")
	public List<SiteSummaryResponse> getSites(CurrentUser currentUser) {
		return siteService.getSites(currentUser);
	}

	@GetMapping("/{siteId}")
	@Operation(summary = "Get a site with its reference profile")
	public SiteResponse getSite(CurrentUser currentUser, @PathVariable String siteId) {
		return siteService.getSite(currentUser, siteId);
	}

}
