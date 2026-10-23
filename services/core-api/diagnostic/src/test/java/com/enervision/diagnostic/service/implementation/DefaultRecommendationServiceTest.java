package com.enervision.diagnostic.service.implementation;

import com.enervision.common.security.CurrentUser;
import com.enervision.common.security.Role;
import com.enervision.configuration.api.dto.SiteResponse;
import com.enervision.configuration.exception.SiteNotFoundException;
import com.enervision.configuration.service.SiteService;
import com.enervision.diagnostic.api.dto.RecommendationItemResponse;
import com.enervision.diagnostic.api.dto.RecommendationResponse;
import com.enervision.diagnostic.entity.HourlyReading;
import com.enervision.diagnostic.repository.HourlyReadingRepository;
import com.enervision.diagnostic.service.rule.LoadRateRecommendationRule;
import com.enervision.diagnostic.service.rule.PowerFactorRecommendationRule;
import com.enervision.diagnostic.service.rule.RecommendationRule;
import com.enervision.diagnostic.service.rule.VoltageRecommendationRule;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;
import java.util.Optional;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class DefaultRecommendationServiceTest {

	private static final CurrentUser USER = new CurrentUser(UUID.randomUUID(), Role.USER);
	private static final String SITE_ID = "SITE001";
	private static final Instant READING_TS = Instant.parse("2026-10-23T10:00:00Z");

	@Mock
	private HourlyReadingRepository hourlyReadingRepository;

	@Mock
	private SiteService siteService;

	private DefaultRecommendationService recommendationService;

	@BeforeEach
	void setUp() {
		List<RecommendationRule> rules = List.of(
				new PowerFactorRecommendationRule(),
				new VoltageRecommendationRule(),
				new LoadRateRecommendationRule());
		recommendationService = new DefaultRecommendationService(hourlyReadingRepository, siteService, rules);
	}

	@Test
	void shouldThrowSiteNotFoundException_whenSiteIsNotVisibleOrDoesNotExist() {
		when(siteService.getSite(USER, SITE_ID)).thenThrow(new SiteNotFoundException(SITE_ID));

		assertThatThrownBy(() -> recommendationService.getRecommendation(USER, SITE_ID))
			.isInstanceOf(SiteNotFoundException.class);
		verifyNoInteractions(hourlyReadingRepository);
	}

	@Test
	void shouldReturnEmptyOptional_whenNoReadingsExistForSite() {
		givenSite(200.0);
		when(hourlyReadingRepository.findFirstBySiteIdOrderByTsDesc(SITE_ID)).thenReturn(Optional.empty());

		Optional<RecommendationResponse> result = recommendationService.getRecommendation(USER, SITE_ID);

		assertThat(result).isEmpty();
	}

	@Test
	void shouldComputeOptimalRecommendations_whenMetricsAreInOptimalRanges() {
		givenSite(200.0);
		HourlyReading reading = reading(400.0, 132.5, 0.98);
		when(hourlyReadingRepository.findFirstBySiteIdOrderByTsDesc(SITE_ID)).thenReturn(Optional.of(reading));

		Optional<RecommendationResponse> result = recommendationService.getRecommendation(USER, SITE_ID);

		assertThat(result).isPresent();
		RecommendationResponse response = result.get();
		assertThat(response.siteId()).isEqualTo(SITE_ID);
		assertThat(response.timestamp()).isEqualTo(READING_TS);
		assertThat(response.items()).hasSize(3);

		RecommendationItemResponse pfItem = response.items().getFirst();
		assertThat(pfItem.type()).isEqualTo("POWER_FACTOR");
		assertThat(pfItem.label()).isEqualTo("Facteur de puissance");
		assertThat(pfItem.value()).isEqualTo(0.98);
		assertThat(pfItem.unit()).isEmpty();
		assertThat(pfItem.quality()).isEqualTo("good");
		assertThat(pfItem.shortRecommendation()).contains("excellent");

		RecommendationItemResponse voltageItem = response.items().get(1);
		assertThat(voltageItem.type()).isEqualTo("VOLTAGE");
		assertThat(voltageItem.label()).isEqualTo("Voltage");
		assertThat(voltageItem.value()).isEqualTo(400.0);
		assertThat(voltageItem.unit()).isEqualTo("V");
		assertThat(voltageItem.quality()).isEqualTo("good");
		assertThat(voltageItem.shortRecommendation()).contains("Tension stable");

		RecommendationItemResponse loadRateItem = response.items().get(2);
		assertThat(loadRateItem.type()).isEqualTo("LOAD_RATE");
		assertThat(loadRateItem.label()).isEqualTo("Taux de charge");
		assertThat(loadRateItem.value()).isEqualTo(42.7);
		assertThat(loadRateItem.unit()).isEqualTo("%");
		assertThat(loadRateItem.quality()).isEqualTo("good");
		assertThat(loadRateItem.shortRecommendation()).contains("optimal");
	}

	@Test
	void shouldComputeMediumRecommendations_whenMetricsAreInMediumRanges() {
		givenSite(200.0);
		HourlyReading reading = reading(430.0, 270.0, 0.94);
		when(hourlyReadingRepository.findFirstBySiteIdOrderByTsDesc(SITE_ID)).thenReturn(Optional.of(reading));

		Optional<RecommendationResponse> result = recommendationService.getRecommendation(USER, SITE_ID);

		assertThat(result).isPresent();
		RecommendationResponse response = result.get();

		RecommendationItemResponse pfItem = response.items().getFirst();
		assertThat(pfItem.value()).isEqualTo(0.94);
		assertThat(pfItem.quality()).isEqualTo("medium");
		assertThat(pfItem.shortRecommendation()).contains("acceptable mais perfectible");

		RecommendationItemResponse voltageItem = response.items().get(1);
		assertThat(voltageItem.value()).isEqualTo(430.0);
		assertThat(voltageItem.quality()).isEqualTo("medium");
		assertThat(voltageItem.shortRecommendation()).contains("Fluctuations de tension");

		RecommendationItemResponse loadRateItem = response.items().get(2);
		assertThat(loadRateItem.value()).isEqualTo(87.0);
		assertThat(loadRateItem.quality()).isEqualTo("medium");
		assertThat(loadRateItem.shortRecommendation()).contains("Taux de charge élevé");
	}

	@Test
	void shouldComputeBadRecommendations_whenMetricsAreInBadRanges() {
		givenSite(200.0);
		HourlyReading reading = reading(350.0, 305.0, 0.85);
		when(hourlyReadingRepository.findFirstBySiteIdOrderByTsDesc(SITE_ID)).thenReturn(Optional.of(reading));

		Optional<RecommendationResponse> result = recommendationService.getRecommendation(USER, SITE_ID);

		assertThat(result).isPresent();
		RecommendationResponse response = result.get();

		RecommendationItemResponse pfItem = response.items().getFirst();
		assertThat(pfItem.value()).isEqualTo(0.85);
		assertThat(pfItem.quality()).isEqualTo("bad");
		assertThat(pfItem.shortRecommendation()).contains("trop faible");

		RecommendationItemResponse voltageItem = response.items().get(1);
		assertThat(voltageItem.value()).isEqualTo(350.0);
		assertThat(voltageItem.quality()).isEqualTo("bad");
		assertThat(voltageItem.shortRecommendation()).contains("Tension critique");

		RecommendationItemResponse loadRateItem = response.items().get(2);
		assertThat(loadRateItem.value()).isEqualTo(98.3);
		assertThat(loadRateItem.quality()).isEqualTo("bad");
		assertThat(loadRateItem.shortRecommendation()).contains("Surcharge imminente");
	}

	@Test
	void shouldHandleNullMetrics_withUnknownQualityAndNullValue() {
		givenSite(201.0);
		HourlyReading reading = reading(null, null, null);
		when(hourlyReadingRepository.findFirstBySiteIdOrderByTsDesc(SITE_ID)).thenReturn(Optional.of(reading));

		Optional<RecommendationResponse> result = recommendationService.getRecommendation(USER, SITE_ID);

		assertThat(result).isPresent();
		for (RecommendationItemResponse item : result.get().items()) {
			assertThat(item.value()).isNull();
			assertThat(item.quality()).isEqualTo("unknown");
			assertThat(item.shortRecommendation()).contains("Données de mesure indisponibles");
		}
	}

	private void givenSite(double capacityKw) {
		when(siteService.getSite(USER, SITE_ID)).thenReturn(new SiteResponse(
				SITE_ID, "Test Site", "office", "Paris", capacityKw, "active", Instant.now(), null));
	}

	private static HourlyReading reading(Double voltageV, Double currentA, Double powerFactor) {
		HourlyReading reading = new HourlyReading();
		reading.setSiteId(SITE_ID);
		reading.setTs(READING_TS);
		reading.setVoltageV(voltageV != null ? BigDecimal.valueOf(voltageV) : null);
		reading.setCurrentA(currentA != null ? BigDecimal.valueOf(currentA) : null);
		reading.setPowerFactor(powerFactor != null ? BigDecimal.valueOf(powerFactor) : null);
		return reading;
	}

}
