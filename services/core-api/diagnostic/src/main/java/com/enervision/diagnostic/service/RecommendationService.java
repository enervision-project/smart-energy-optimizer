package com.enervision.diagnostic.service;

import com.enervision.common.security.CurrentUser;
import com.enervision.diagnostic.api.dto.RecommendationResponse;

import java.util.Optional;

public interface RecommendationService {

	Optional<RecommendationResponse> getRecommendation(CurrentUser user, String siteId);

}
