package com.enervision.diagnostic.service;

import com.enervision.common.security.CurrentUser;
import com.enervision.diagnostic.api.dto.RecommendationResponse;

import java.util.Optional;

public interface RecommendationService {

	/**
	 * Compute recommendations for a site based on its latest hourly readings.
	 *
	 * @param user current authenticated user
	 * @param siteId site identifier
	 * @return recommendations, or {@code Optional.empty()} if no readings exist for this site
	 */
	Optional<RecommendationResponse> getRecommendation(CurrentUser user, String siteId);

}
