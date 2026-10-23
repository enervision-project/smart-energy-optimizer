package com.enervision.diagnostic.service.implementation;

import com.enervision.common.security.CurrentUser;
import com.enervision.configuration.api.dto.SiteResponse;
import com.enervision.configuration.service.SiteService;
import com.enervision.diagnostic.api.dto.RecommendationItemResponse;
import com.enervision.diagnostic.api.dto.RecommendationResponse;
import com.enervision.diagnostic.entity.HourlyReading;
import com.enervision.diagnostic.repository.HourlyReadingRepository;
import com.enervision.diagnostic.service.RecommendationService;
import com.enervision.diagnostic.service.rule.RecommendationRule;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;
import java.util.Optional;

@Service
@RequiredArgsConstructor
@Transactional(readOnly = true)
class DefaultRecommendationService implements RecommendationService {

	private final HourlyReadingRepository hourlyReadingRepository;
	private final SiteService siteService;
	private final List<RecommendationRule> rules;

	@Override
	public Optional<RecommendationResponse> getRecommendation(CurrentUser user, String siteId) {
		SiteResponse site = siteService.getSite(user, siteId);
		Optional<HourlyReading> latestReading = hourlyReadingRepository.findFirstBySiteIdOrderByTsDesc(siteId);
		if (latestReading.isEmpty()) {
			return Optional.empty();
		}

		HourlyReading reading = latestReading.get();
		List<RecommendationItemResponse> items = rules.stream()
			.map(rule -> rule.evaluate(site, reading))
			.toList();

		return Optional.of(new RecommendationResponse(siteId, reading.getTs(), items));
	}

}
