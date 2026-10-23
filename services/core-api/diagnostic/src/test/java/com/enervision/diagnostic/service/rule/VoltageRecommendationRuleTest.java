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

class VoltageRecommendationRuleTest {

	private final VoltageRecommendationRule rule = new VoltageRecommendationRule();

	@Test
	void shouldHaveVoltageType() {
		assertThat(rule.type()).isEqualTo(RecommendationType.VOLTAGE);
	}

	@Test
	void shouldReturnMissing_whenVoltageIsNull() {
		HourlyReading reading = new HourlyReading();

		RecommendationItemResponse response = rule.evaluate(site(200.0), reading);

		assertThat(response.quality()).isEqualTo(RecommendationQuality.UNKNOWN.code());
		assertThat(response.value()).isNull();
		assertThat(response.shortRecommendation()).contains("indisponibles");
	}

	@Test
	void shouldReturnGood_whenVoltageWithinFivePercent() {
		HourlyReading reading = new HourlyReading();
		reading.setVoltageV(BigDecimal.valueOf(420.0)); // Exactly +5%

		RecommendationItemResponse response = rule.evaluate(site(200.0), reading);

		assertThat(response.quality()).isEqualTo(RecommendationQuality.GOOD.code());
		assertThat(response.value()).isEqualTo(420.0);
		assertThat(response.shortRecommendation()).contains("Tension stable");
	}

	@Test
	void shouldReturnMedium_whenVoltageBetweenFiveAndTenPercent() {
		HourlyReading reading = new HourlyReading();
		reading.setVoltageV(BigDecimal.valueOf(370.0)); // 7.5% deviation

		RecommendationItemResponse response = rule.evaluate(site(200.0), reading);

		assertThat(response.quality()).isEqualTo(RecommendationQuality.MEDIUM.code());
		assertThat(response.value()).isEqualTo(370.0);
		assertThat(response.shortRecommendation()).contains("Fluctuations");
	}

	@Test
	void shouldReturnBad_whenVoltageAboveTenPercent() {
		HourlyReading reading = new HourlyReading();
		reading.setVoltageV(BigDecimal.valueOf(445.0)); // 11.25% deviation

		RecommendationItemResponse response = rule.evaluate(site(201.0), reading);

		assertThat(response.quality()).isEqualTo(RecommendationQuality.BAD.code());
		assertThat(response.value()).isEqualTo(445.0);
		assertThat(response.shortRecommendation()).contains("Tension critique");
	}

	private static SiteResponse site(double capacityKw) {
		return new SiteResponse("S1", "Site 1", "office", "Paris", capacityKw, "active", Instant.now(), null);
	}

}
