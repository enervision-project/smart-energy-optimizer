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

class LoadRateRecommendationRuleTest {

	private final LoadRateRecommendationRule rule = new LoadRateRecommendationRule();

	@Test
	void shouldHaveLoadRateType() {
		assertThat(rule.type()).isEqualTo(RecommendationType.LOAD_RATE);
	}

	@Test
	void shouldReturnMissing_whenCurrentIsNull() {
		HourlyReading reading = new HourlyReading();

		RecommendationItemResponse response = rule.evaluate(site(200.0), reading);

		assertThat(response.quality()).isEqualTo(RecommendationQuality.UNKNOWN.code());
		assertThat(response.value()).isNull();
		assertThat(response.shortRecommendation()).contains("indisponibles");
	}

	@Test
	void shouldReturnMissing_whenCapacityKwIsZero() {
		HourlyReading reading = new HourlyReading();
		reading.setCurrentA(BigDecimal.valueOf(100.0));

		RecommendationItemResponse response = rule.evaluate(site(0.0), reading);

		assertThat(response.quality()).isEqualTo(RecommendationQuality.UNKNOWN.code());
		assertThat(response.value()).isNull();
	}

	@Test
	void shouldReturnGood_whenLoadRateBelowOrEqualEightyPercent() {
		// Capacity 200 kW -> I_nominale ~310.32 A. 132.5 A -> 42.7%
		HourlyReading reading = new HourlyReading();
		reading.setCurrentA(BigDecimal.valueOf(132.5));

		RecommendationItemResponse response = rule.evaluate(site(200.0), reading);

		assertThat(response.quality()).isEqualTo(RecommendationQuality.GOOD.code());
		assertThat(response.value()).isEqualTo(42.7);
		assertThat(response.shortRecommendation()).contains("optimal");
	}

	@Test
	void shouldReturnMedium_whenLoadRateBetweenEightyAndNinetyFivePercent() {
		// Capacity 200 kW -> 270 A -> ~87.0%
		HourlyReading reading = new HourlyReading();
		reading.setCurrentA(BigDecimal.valueOf(270.0));

		RecommendationItemResponse response = rule.evaluate(site(200.0), reading);

		assertThat(response.quality()).isEqualTo(RecommendationQuality.MEDIUM.code());
		assertThat(response.value()).isEqualTo(87.0);
		assertThat(response.shortRecommendation()).contains("Taux de charge élevé");
	}

	@Test
	void shouldReturnBad_whenLoadRateAboveNinetyFivePercent() {
		// Capacity 200 kW -> 305 A -> ~98.3%
		HourlyReading reading = new HourlyReading();
		reading.setCurrentA(BigDecimal.valueOf(305.0));

		RecommendationItemResponse response = rule.evaluate(site(200.0), reading);

		assertThat(response.quality()).isEqualTo(RecommendationQuality.BAD.code());
		assertThat(response.value()).isEqualTo(98.3);
		assertThat(response.shortRecommendation()).contains("Surcharge imminente");
	}

	private static SiteResponse site(double capacityKw) {
		return new SiteResponse("S1", "Site 1", "office", "Paris", capacityKw, "active", Instant.now(), null);
	}

}
