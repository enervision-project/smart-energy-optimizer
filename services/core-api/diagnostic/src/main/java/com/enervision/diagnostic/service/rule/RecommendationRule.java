package com.enervision.diagnostic.service.rule;

import com.enervision.configuration.api.dto.SiteResponse;
import com.enervision.diagnostic.api.dto.RecommendationItemResponse;
import com.enervision.diagnostic.entity.HourlyReading;
import com.enervision.diagnostic.entity.RecommendationType;

import java.math.BigDecimal;
import java.math.RoundingMode;

public interface RecommendationRule {

	RecommendationType type();

	RecommendationItemResponse evaluate(SiteResponse site, HourlyReading reading);

	static double round(double value, int scale) {
		return BigDecimal.valueOf(value).setScale(scale, RoundingMode.HALF_UP).doubleValue();
	}

}
