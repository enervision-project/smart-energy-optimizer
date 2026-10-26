package com.enervision.telemetry.service.implementation;

import com.enervision.common.security.CurrentUser;
import com.enervision.common.security.Role;
import com.enervision.configuration.api.dto.SiteSummaryResponse;
import com.enervision.configuration.service.SiteService;
import com.enervision.telemetry.api.dto.ParkSummaryResponse;
import com.enervision.telemetry.api.dto.SiteLoadResponse;
import com.enervision.telemetry.repository.ReadingRepository;
import com.enervision.telemetry.repository.ReadingRow;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.List;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class DefaultParkServiceTest {

	private static final Instant NOW = Instant.parse("2026-10-26T10:07:30Z");
	private static final CurrentUser USER = new CurrentUser(UUID.randomUUID(), Role.USER);

	@Mock
	private ReadingRepository readingRepository;

	@Mock
	private SiteService siteService;

	private DefaultParkService parkService;

	@BeforeEach
	void setUp() {
		parkService = new DefaultParkService(readingRepository, siteService, Clock.fixed(NOW, ZoneOffset.UTC));
	}

	@Test
	void shouldSumCurrentConsumption_andListSitesWithoutData() {
		// given: SITE001 raw value, SITE003 sensor failure with an imputed value, SITE005 NULL, SITE007 no reading
		when(siteService.getSites(USER)).thenReturn(List.of(
				site("SITE007", 300), site("SITE001", 200), site("SITE003", 800), site("SITE005", 600)));
		Instant ts = Instant.parse("2026-10-26T10:07:00Z");
		when(readingRepository.findLatestPerSite(List.of("SITE001", "SITE003", "SITE005", "SITE007"),
				NOW.minus(Duration.ofMinutes(3))))
			.thenReturn(List.of(
					reading("SITE001", ts, 87.34, null, "good"),
					reading("SITE003", ts, null, 520.0, "degraded"),
					reading("SITE005", ts, null, null, "critical")));

		// when
		ParkSummaryResponse summary = parkService.getSummary(USER);

		// then
		assertThat(summary.totalSites()).isEqualTo(4);
		assertThat(summary.totalConsumptionKw()).isEqualTo(607.34);
		assertThat(summary.totalCapacityKw()).isEqualTo(1900);
		assertThat(summary.averageLoadPercent()).isEqualTo(32.0);
		assertThat(summary.sitesWithoutData()).containsExactly("SITE005", "SITE007");
		assertThat(summary.sites()).extracting(SiteLoadResponse::siteId)
			.containsExactly("SITE001", "SITE003", "SITE005", "SITE007");

		SiteLoadResponse imputed = summary.sites().get(1);
		assertThat(imputed.currentConsumptionKw()).isEqualTo(520.0);
		assertThat(imputed.consumptionImputed()).isTrue();
		assertThat(imputed.loadPercent()).isEqualTo(65.0);
		assertThat(imputed.ageSeconds()).isEqualTo(30);

		SiteLoadResponse noReading = summary.sites().get(3);
		assertThat(noReading.currentConsumptionKw()).isNull();
		assertThat(noReading.dataQuality()).isNull();
		assertThat(noReading.ts()).isNull();
	}

	@Test
	void shouldReturnEmptySummary_withoutQuerying_whenUserHasNoSite() {
		// given
		when(siteService.getSites(USER)).thenReturn(List.of());

		// when
		ParkSummaryResponse summary = parkService.getSummary(USER);

		// then
		assertThat(summary.totalSites()).isZero();
		assertThat(summary.averageLoadPercent()).isNull();
		assertThat(summary.sites()).isEmpty();
		verifyNoInteractions(readingRepository);
	}

	private static SiteSummaryResponse site(String siteId, double capacityKw) {
		return new SiteSummaryResponse(siteId, "Site " + siteId, "office", "Paris", capacityKw, "active");
	}

	private static ReadingRow reading(String siteId, Instant ts, Double raw, Double imputed, String quality) {
		return new ReadingRow(siteId, ts, "current", raw, imputed, imputed == null ? null : "previous_value", 230.0,
				10.0, 0.9, 20.0, 40.0, List.of(), quality);
	}

}
