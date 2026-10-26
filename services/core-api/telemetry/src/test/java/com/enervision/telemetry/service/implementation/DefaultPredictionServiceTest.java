package com.enervision.telemetry.service.implementation;

import com.enervision.common.security.CurrentUser;
import com.enervision.common.security.Role;
import com.enervision.configuration.api.dto.SiteSummaryResponse;
import com.enervision.configuration.service.SiteService;
import com.enervision.telemetry.api.dto.PredictionPointResponse;
import com.enervision.telemetry.api.dto.PredictionSeriesResponse;
import com.enervision.telemetry.entity.Prediction;
import com.enervision.telemetry.entity.PredictionRun;
import com.enervision.telemetry.exception.InvalidPredictionPeriodException;
import com.enervision.telemetry.exception.TelemetrySiteNotFoundException;
import com.enervision.telemetry.mapper.PredictionMapper;
import com.enervision.telemetry.repository.PredictionRepository;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.math.BigDecimal;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.List;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class DefaultPredictionServiceTest {

	private static final String SITE = "SITE001";
	private static final CurrentUser USER = new CurrentUser(UUID.randomUUID(), Role.USER);
	private static final Instant NOW = Instant.parse("2026-10-26T10:07:30Z");
	private static final Instant START = Instant.parse("2026-10-26T08:00:00Z");
	private static final UUID RUN_ID = UUID.fromString("00000000-0000-0000-0000-000000000003");

	@Mock
	private PredictionRepository predictionRepository;

	@Mock
	private SiteService siteService;

	private DefaultPredictionService predictionService;

	@BeforeEach
	void setUp() {
		predictionService = new DefaultPredictionService(predictionRepository, siteService, new PredictionMapper(),
				Clock.fixed(NOW, ZoneOffset.UTC));
	}

	@Test
	void shouldReturn24HourlyGaps_whenNoPeriodOrForecastIsAvailable() {
		// given
		givenVisible(USER);

		// when
		PredictionSeriesResponse series = predictionService.getPredictions(USER, SITE, null, null);

		// then
		Instant start = Instant.parse("2026-10-26T10:00:00Z");
		assertThat(series.siteId()).isEqualTo(SITE);
		assertThat(series.step()).isEqualTo("1h");
		assertThat(series.from()).isEqualTo(start);
		assertThat(series.to()).isEqualTo(start.plus(Duration.ofHours(24)));
		assertThat(series.points()).hasSize(24).allSatisfy(point -> {
			assertThat(point.predictionKwh()).isNull();
			assertThat(point.runId()).isNull();
			assertThat(point.modelName()).isNull();
			assertThat(point.modelVersion()).isNull();
			assertThat(point.generatedAt()).isNull();
		});
		assertThat(series.points().getLast().ts()).isEqualTo(start.plus(Duration.ofHours(23)));
		verify(predictionRepository).findLatestForSite(SITE, series.from(), series.to());
	}

	@Test
	void shouldAlignSortAndFillGaps_preservingZeroPrecisionAndPublicationMetadata() {
		// given
		givenVisible(USER);
		when(predictionRepository.findLatestForSite(SITE, START, START.plus(Duration.ofHours(3))))
			.thenReturn(List.of(prediction(START.plus(Duration.ofHours(2)), "123.456"), prediction(START, "0.000")));

		// when
		PredictionSeriesResponse series = predictionService.getPredictions(USER, SITE, START.plusSeconds(60),
				START.plus(Duration.ofHours(2)).plusSeconds(60));

		// then
		assertThat(series.points()).extracting(PredictionPointResponse::ts)
			.containsExactly(START, START.plus(Duration.ofHours(1)), START.plus(Duration.ofHours(2)));
		assertThat(series.points().getFirst().predictionKwh()).isEqualByComparingTo("0");
		assertThat(series.points().get(1).predictionKwh()).isNull();
		PredictionPointResponse point = series.points().getLast();
		assertThat(point.predictionKwh()).isEqualByComparingTo("123.456");
		assertThat(point.runId()).isEqualTo(RUN_ID);
		assertThat(point.modelName()).isEqualTo("hourly-consumption");
		assertThat(point.modelVersion()).isEqualTo("3");
		assertThat(point.generatedAt()).isEqualTo(START.minus(Duration.ofHours(2)));
	}

	@Test
	void shouldDerive24HoursAfterTheAlignedStart_whenOnlyFromIsProvided() {
		givenVisible(USER);
		PredictionSeriesResponse series = predictionService.getPredictions(USER, SITE, START.plusSeconds(120), null);
		assertThat(series.from()).isEqualTo(START);
		assertThat(series.to()).isEqualTo(START.plus(Duration.ofHours(24)));
		assertThat(series.points()).hasSize(24);
	}

	@Test
	void shouldDerive24HoursBeforeTheAlignedEnd_whenOnlyToIsProvided() {
		givenVisible(USER);
		PredictionSeriesResponse series = predictionService.getPredictions(USER, SITE, null, START.plusSeconds(120));
		assertThat(series.to()).isEqualTo(START.plus(Duration.ofHours(1)));
		assertThat(series.from()).isEqualTo(series.to().minus(Duration.ofHours(24)));
		assertThat(series.points()).hasSize(24);
	}

	@Test
	void shouldPreserveAnAlignedExclusiveEnd() {
		givenVisible(USER);
		PredictionSeriesResponse series = predictionService.getPredictions(USER, SITE, START,
				START.plus(Duration.ofHours(1)));
		assertThat(series.points()).extracting(PredictionPointResponse::ts).containsExactly(START);
		assertThat(series.to()).isEqualTo(START.plus(Duration.ofHours(1)));
	}

	@Test
	void shouldRejectEqualOrInvertedBounds_evenWithinTheSameHour() {
		givenVisible(USER);
		assertThatThrownBy(() -> predictionService.getPredictions(USER, SITE, NOW, NOW))
			.isInstanceOf(InvalidPredictionPeriodException.class);
		assertThatThrownBy(() -> predictionService.getPredictions(USER, SITE, NOW, NOW.minusSeconds(1)))
			.isInstanceOf(InvalidPredictionPeriodException.class);
		verifyNoInteractions(predictionRepository);
	}

	@Test
	void shouldRejectAPeriodLongerThan366Days_afterHourAlignment() {
		givenVisible(USER);
		assertThatThrownBy(() -> predictionService.getPredictions(USER, SITE, START,
				START.plus(Duration.ofDays(366)).plusSeconds(1)))
			.isInstanceOf(InvalidPredictionPeriodException.class)
			.hasMessageContaining("366 days");
		verifyNoInteractions(predictionRepository);
	}

	@Test
	void shouldAcceptExactlyTheMaximumPeriod() {
		givenVisible(USER);
		PredictionSeriesResponse series = predictionService.getPredictions(USER, SITE, START,
				START.plus(Duration.ofDays(366)));
		assertThat(series.points()).hasSize(366 * 24);
	}

	@Test
	void shouldRejectAnInaccessibleSite_beforeQueryingPredictions() {
		when(siteService.getSites(USER)).thenReturn(List.of());
		assertThatThrownBy(() -> predictionService.getPredictions(USER, SITE, null, null))
			.isInstanceOf(TelemetrySiteNotFoundException.class);
		verifyNoInteractions(predictionRepository);
	}

	@Test
	void shouldRejectANonexistentSite_evenForAnAdmin() {
		CurrentUser admin = new CurrentUser(UUID.randomUUID(), Role.ADMIN);
		when(siteService.getSites(admin)).thenReturn(List.of());
		assertThatThrownBy(() -> predictionService.getPredictions(admin, "MISSING", null, null))
			.isInstanceOf(TelemetrySiteNotFoundException.class);
		verifyNoInteractions(predictionRepository);
	}

	@Test
	void shouldAllowAnAdminToReadAnExistingVisibleSite() {
		CurrentUser admin = new CurrentUser(UUID.randomUUID(), Role.ADMIN);
		givenVisible(admin);
		predictionService.getPredictions(admin, SITE, START, START.plus(Duration.ofHours(1)));
		verify(predictionRepository).findLatestForSite(eq(SITE), any(), any());
	}

	@Test
	void shouldKeepBothInstants_whenParisRepeatsTheSameLocalHour() {
		givenVisible(USER);
		Instant from = OffsetDateTime.parse("2026-10-25T02:00:00+02:00").toInstant();
		Instant to = OffsetDateTime.parse("2026-10-25T03:00:00+01:00").toInstant();
		PredictionSeriesResponse series = predictionService.getPredictions(USER, SITE, from, to);
		assertThat(series.points()).extracting(PredictionPointResponse::ts)
			.containsExactly(Instant.parse("2026-10-25T00:00:00Z"), Instant.parse("2026-10-25T01:00:00Z"));
	}

	private void givenVisible(CurrentUser user) {
		when(siteService.getSites(user))
			.thenReturn(List.of(new SiteSummaryResponse(SITE, "Office", "office", "Paris", 200, "active")));
	}

	private static Prediction prediction(Instant ts, String value) {
		PredictionRun run = new PredictionRun();
		run.setRunId(RUN_ID);
		run.setModelName("hourly-consumption");
		run.setModelVersion("3");
		run.setGeneratedAt(START.minus(Duration.ofHours(2)));
		run.setStatus("complete");
		Prediction prediction = new Prediction();
		prediction.setRun(run);
		prediction.setSiteId(SITE);
		prediction.setPredictedFor(ts);
		prediction.setPredictionKwh(new BigDecimal(value));
		return prediction;
	}

}
