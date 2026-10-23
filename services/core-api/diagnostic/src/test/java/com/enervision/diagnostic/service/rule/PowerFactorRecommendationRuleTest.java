package com.enervision.diagnostic.service.rule;

import com.enervision.configuration.api.dto.SiteResponse;
import com.enervision.diagnostic.api.dto.RecommendationItemResponse;
import com.enervision.diagnostic.entity.HourlyReading;
import com.enervision.diagnostic.entity.RecommendationQuality;
import com.enervision.diagnostic.entity.RecommendationType;
import org.junit.jupiter.api.Test;

import java.math.BigDecimal;
import java.time.Instant;

import static org.assertj.core.api.Assertions.assertThat;

class PowerFactorRecommendationRuleTest {

	private final PowerFactorRecommendationRule rule = new PowerFactorRecommendationRule();

	@Test
	void shouldHavePowerFactorType() {
		assertThat(rule.type()).isEqualTo(RecommendationType.POWER_FACTOR);
	}

	@Test
	void shouldReturnMissing_whenPowerFactorIsNull() {
		HourlyReading reading = new HourlyReading();

		RecommendationItemResponse response = rule.evaluate(site(200.0), reading);

		assertThat(response.quality()).isEqualTo(RecommendationQuality.UNKNOWN.code());
		assertThat(response.value()).isNull();
		assertThat(response.shortRecommendation()).contains("indisponibles");
	}

	@Test
	void shouldReturnGood_whenPowerFactorIsAboveOrEqualThreshold() {
		HourlyReading reading = new HourlyReading();
		reading.setPowerFactor(BigDecimal.valueOf(0.95));

		RecommendationItemResponse response = rule.evaluate(site(200.0), reading);

		assertThat(response.quality()).isEqualTo(RecommendationQuality.GOOD.code());
		assertThat(response.value()).isEqualTo(0.95);
		assertThat(response.shortRecommendation()).contains("excellent");
	}

	@Test
	void shouldReturnMedium_whenPowerFactorIsBetweenThresholds() {
		HourlyReading reading = new HourlyReading();
		reading.setPowerFactor(BigDecimal.valueOf(0.93));

		RecommendationItemResponse response = rule.evaluate(site(200.0), reading);

		assertThat(response.quality()).isEqualTo(RecommendationQuality.MEDIUM.code());
		assertThat(response.value()).isEqualTo(0.93);
		assertThat(response.shortRecommendation()).contains("acceptable mais perfectible");
	}

	@Test
	void shouldReturnBad_whenPowerFactorIsBelowThreshold() {
		HourlyReading reading = new HourlyReading();
		reading.setPowerFactor(BigDecimal.valueOf(0.92));

		RecommendationItemResponse response = rule.evaluate(site(201.0), reading);

		assertThat(response.quality()).isEqualTo(RecommendationQuality.BAD.code());
		assertThat(response.value()).isEqualTo(0.92);
		assertThat(response.shortRecommendation()).contains("trop faible");
	}

	private static SiteResponse site(double capacityKw) {
		return new SiteResponse("S1", "Site 1", "office", "Paris", capacityKw, "active", Instant.now(), null);
	}

}
