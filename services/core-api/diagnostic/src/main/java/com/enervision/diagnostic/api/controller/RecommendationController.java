package com.enervision.diagnostic.api.controller;

import com.enervision.common.security.CurrentUser;
import com.enervision.diagnostic.api.dto.RecommendationResponse;
import com.enervision.diagnostic.service.RecommendationService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import lombok.RequiredArgsConstructor;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/v1/recommendations")
@RequiredArgsConstructor
@Tag(name = "Recommendations")
public class RecommendationController {

	private final RecommendationService recommendationService;

	@GetMapping("/{siteId}")
	@Operation(summary = "Get energy recommendations for a site based on its latest hourly readings")
	public ResponseEntity<RecommendationResponse> getRecommendation(
			CurrentUser currentUser,
			@PathVariable String siteId) {
		return recommendationService.getRecommendation(currentUser, siteId)
			.map(ResponseEntity::ok)
			.orElseGet(() -> ResponseEntity.noContent().build());
	}

}
