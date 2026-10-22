package com.enervision.diagnostic.service.implementation;

import com.enervision.common.security.CurrentUser;
import com.enervision.common.security.Role;
import com.enervision.configuration.api.dto.SiteSummaryResponse;
import com.enervision.configuration.service.SiteService;
import com.enervision.diagnostic.api.dto.AlertResponse;
import com.enervision.diagnostic.api.dto.AlertSearchRequest;
import com.enervision.diagnostic.api.dto.AlertSummaryResponse;
import com.enervision.diagnostic.entity.Alert;
import com.enervision.diagnostic.exception.AlertSiteNotFoundException;
import com.enervision.diagnostic.exception.InvalidAlertPeriodException;
import com.enervision.diagnostic.mapper.AlertMapper;
import com.enervision.diagnostic.repository.AlertRepository;
import com.enervision.diagnostic.repository.SeverityCount;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageImpl;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;
import org.springframework.data.jpa.domain.Specification;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class DefaultAlertServiceTest {

	private static final Instant NOW = Instant.parse("2026-10-22T11:00:00Z");
	private static final CurrentUser USER = new CurrentUser(UUID.randomUUID(), Role.USER);
	private static final AlertSearchRequest NO_FILTER = new AlertSearchRequest(null, null, null, null, null);

	@Mock
	private AlertRepository alertRepository;

	@Mock
	private SiteService siteService;

	private DefaultAlertService alertService;

	@BeforeEach
	void setUp() {
		alertService = new DefaultAlertService(
				alertRepository, siteService, new AlertMapper(), Clock.fixed(NOW, ZoneOffset.UTC));
	}

	@Test
	void shouldReturnAlertsWithSiteNameAndRecentFlag_whenNoFilter() {
		// given
		givenVisibleSites("SITE001", "SITE002");
		Alert recent = alert("ALR-1", "SITE002", NOW.minusSeconds(60));
		Alert old = alert("ALR-2", "SITE001", NOW.minusSeconds(7200));
		when(alertRepository.findAll(anySpecification(), any(Pageable.class)))
			.thenReturn(new PageImpl<>(List.of(recent, old)));

		// when
		Page<AlertResponse> alerts = alertService.getAlerts(USER, NO_FILTER, 0, 50);

		// then
		assertThat(alerts.getContent()).extracting(AlertResponse::siteName)
			.containsExactly("Site SITE002", "Site SITE001");
		assertThat(alerts.getContent()).extracting(AlertResponse::recent).containsExactly(true, false);
	}

	@Test
	void shouldSortNewestFirst_whenListingAlerts() {
		// given
		givenVisibleSites("SITE001");
		when(alertRepository.findAll(anySpecification(), any(Pageable.class))).thenReturn(Page.empty());
		ArgumentCaptor<Pageable> pageable = ArgumentCaptor.forClass(Pageable.class);

		// when
		alertService.getAlerts(USER, NO_FILTER, 2, 20);

		// then
		verify(alertRepository).findAll(anySpecification(), pageable.capture());
		assertThat(pageable.getValue().getPageNumber()).isEqualTo(2);
		assertThat(pageable.getValue().getPageSize()).isEqualTo(20);
		assertThat(pageable.getValue().getSort().getOrderFor("timestamp"))
			.isEqualTo(Sort.Order.desc("timestamp"));
	}

	@Test
	void shouldReturnEmptyPage_withoutQuerying_whenUserHasNoSite() {
		// given
		when(siteService.getSites(USER)).thenReturn(List.of());

		// when
		Page<AlertResponse> alerts = alertService.getAlerts(USER, NO_FILTER, 0, 50);

		// then
		assertThat(alerts).isEmpty();
		verifyNoInteractions(alertRepository);
	}

	@Test
	void shouldThrowSiteNotFound_whenSiteIsNotVisible() {
		// given
		givenVisibleSites("SITE001");
		AlertSearchRequest request = new AlertSearchRequest("SITE002", null, null, null, null);

		// when / then
		assertThatThrownBy(() -> alertService.getAlerts(USER, request, 0, 50))
			.isInstanceOf(AlertSiteNotFoundException.class);
		verifyNoInteractions(alertRepository);
	}

	@Test
	void shouldThrowInvalidPeriod_whenFromIsAfterTo() {
		// given
		givenVisibleSites("SITE001");
		AlertSearchRequest request = new AlertSearchRequest(null, null, null, NOW, NOW.minusSeconds(1));

		// when / then
		assertThatThrownBy(() -> alertService.getAlerts(USER, request, 0, 50))
			.isInstanceOf(InvalidAlertPeriodException.class);
		verifyNoInteractions(alertRepository);
	}

	@Test
	void shouldCountRecentAlertsPerSeverity_withZerosAndUnknownSeverities() {
		// given
		givenVisibleSites("SITE001", "SITE002");
		Instant since = NOW.minus(DefaultAlertService.RECENT_PERIOD);
		when(alertRepository.countBySeveritySince(Set.of("SITE001", "SITE002"), since)).thenReturn(List.of(
				new SeverityCount("high", 2),
				new SeverityCount("low", 1),
				new SeverityCount("urgent", 4)));

		// when
		AlertSummaryResponse summary = alertService.getSummary(USER, null);

		// then
		assertThat(summary.since()).isEqualTo(since);
		assertThat(summary.total()).isEqualTo(7);
		assertThat(summary.bySeverity()).containsExactly(
				Map.entry("low", 1L), Map.entry("medium", 0L), Map.entry("high", 2L), Map.entry("critical", 0L));
	}

	@Test
	void shouldCountOnlyTheGivenSite_whenSiteIsGiven() {
		// given
		givenVisibleSites("SITE001", "SITE002");
		when(alertRepository.countBySeveritySince(eq(Set.of("SITE002")), any())).thenReturn(List.of());

		// when
		AlertSummaryResponse summary = alertService.getSummary(USER, "SITE002");

		// then
		assertThat(summary.total()).isZero();
	}

	private void givenVisibleSites(String... siteIds) {
		when(siteService.getSites(USER)).thenReturn(List.of(siteIds).stream()
			.map(siteId -> new SiteSummaryResponse(siteId, "Site " + siteId, "office", "Paris", 200, "active"))
			.toList());
	}

	@SuppressWarnings("unchecked")
	private static Specification<Alert> anySpecification() {
		return any(Specification.class);
	}

	private static Alert alert(String alertId, String siteId, Instant timestamp) {
		Alert alert = new Alert();
		alert.setAlertId(alertId);
		alert.setSiteId(siteId);
		alert.setTimestamp(timestamp);
		alert.setSeverity("high");
		alert.setType("spike");
		alert.setMessage("Pic de consommation détecté sur Site " + siteId);
		alert.setValue(912.5);
		alert.setThreshold(720.0);
		return alert;
	}

}
