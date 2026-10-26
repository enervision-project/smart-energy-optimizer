package com.enervision.telemetry.service.implementation;

import com.enervision.common.security.CurrentUser;
import com.enervision.common.security.Role;
import com.enervision.configuration.api.dto.SiteSummaryResponse;
import com.enervision.configuration.service.SiteService;
import com.enervision.telemetry.api.dto.LatestReadingResponse;
import com.enervision.telemetry.api.dto.ReadingPoint;
import com.enervision.telemetry.api.dto.ReadingSeriesResponse;
import com.enervision.telemetry.api.dto.ReadingStep;
import com.enervision.telemetry.api.dto.ReadingSummaryResponse;
import com.enervision.telemetry.exception.InvalidReadingPeriodException;
import com.enervision.telemetry.exception.TelemetrySiteNotFoundException;
import com.enervision.telemetry.repository.BucketRow;
import com.enervision.telemetry.repository.ReadingRepository;
import com.enervision.telemetry.repository.ReadingRow;
import com.enervision.telemetry.repository.SummaryRow;
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
import java.util.Optional;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class DefaultReadingServiceTest {

	/** 10:07:30 UTC: the 10:00 quarter is in progress, the 10:07 minute too. */
	private static final Instant NOW = Instant.parse("2026-10-26T10:07:30Z");
	private static final CurrentUser USER = new CurrentUser(UUID.randomUUID(), Role.USER);
	private static final String SITE = "SITE001";

	@Mock
	private ReadingRepository readingRepository;

	@Mock
	private SiteService siteService;

	private DefaultReadingService readingService;

	@BeforeEach
	void setUp() {
		readingService = new DefaultReadingService(readingRepository, siteService, Clock.fixed(NOW, ZoneOffset.UTC));
	}

	@Test
	void shouldReturnEveryStepOfTheLast48Hours_withGapsAndElapsedMinutes_whenNoPeriod() {
		// given
		givenVisible();
		Instant lastQuarter = Instant.parse("2026-10-26T10:00:00Z");
		when(readingRepository.findBuckets(eq(SITE), eq(Duration.ofMinutes(15)), any(), any()))
			.thenReturn(List.of(bucket(lastQuarter.minus(Duration.ofMinutes(15))), bucket(lastQuarter)));

		// when
		ReadingSeriesResponse series = readingService.getReadings(USER, SITE, null, null, ReadingStep.FIFTEEN_MINUTES);

		// then
		Instant end = Instant.parse("2026-10-26T10:15:00Z");
		assertThat(series.step()).isEqualTo("15m");
		assertThat(series.to()).isEqualTo(end);
		assertThat(series.from()).isEqualTo(end.minus(Duration.ofHours(48)));
		assertThat(series.points()).hasSize(48 * 4);
		verify(readingRepository).findBuckets(SITE, Duration.ofMinutes(15), series.from(), end);

		ReadingPoint gap = series.points().getFirst();
		assertThat(gap.ts()).isEqualTo(series.from());
		assertThat(gap.consumptionKw()).isNull();
		assertThat(gap.dataQuality()).isNull();
		assertThat(gap.minutesExpected()).isEqualTo(15);
		assertThat(gap.minutesReceived()).isZero();

		ReadingPoint complete = series.points().get(series.points().size() - 2);
		assertThat(complete.consumptionKw()).isEqualTo(120.5);
		assertThat(complete.dataQuality()).isEqualTo("degraded");
		assertThat(complete.minutesExpected()).isEqualTo(15);

		// 10:00 to 10:07 elapsed: the quarter in progress is not reported incomplete.
		ReadingPoint inProgress = series.points().getLast();
		assertThat(inProgress.ts()).isEqualTo(lastQuarter);
		assertThat(inProgress.minutesExpected()).isEqualTo(7);
	}

	@Test
	void shouldAlignAnExplicitPeriodOnTheStep() {
		// given
		givenVisible();
		Instant from = Instant.parse("2026-10-26T08:20:00Z");
		Instant to = Instant.parse("2026-10-26T09:10:00Z");

		// when
		ReadingSeriesResponse series = readingService.getReadings(USER, SITE, from, to, ReadingStep.ONE_HOUR);

		// then
		assertThat(series.from()).isEqualTo(Instant.parse("2026-10-26T08:00:00Z"));
		assertThat(series.to()).isEqualTo(Instant.parse("2026-10-26T10:00:00Z"));
		assertThat(series.points()).extracting(ReadingPoint::minutesExpected).containsExactly(60, 60);
	}

	@Test
	void shouldRejectAPeriodLongerThanTheStepAllows() {
		// given
		givenVisible();
		Instant from = NOW.minus(Duration.ofHours(49));

		// when / then
		assertThatThrownBy(() -> readingService.getReadings(USER, SITE, from, NOW, ReadingStep.ONE_MINUTE))
			.isInstanceOf(InvalidReadingPeriodException.class)
			.hasMessageContaining("48 hours");
		verifyNoInteractions(readingRepository);
	}

	@Test
	void shouldRejectAnEmptyPeriod() {
		// given
		givenVisible();

		// when / then
		assertThatThrownBy(() -> readingService.getReadings(USER, SITE, NOW, NOW.minusSeconds(3600),
				ReadingStep.FIFTEEN_MINUTES))
			.isInstanceOf(InvalidReadingPeriodException.class);
		verifyNoInteractions(readingRepository);
	}

	@Test
	void shouldThrowSiteNotFound_withoutQuerying_whenSiteIsNotVisible() {
		// given
		when(siteService.getSites(USER)).thenReturn(List.of(site("SITE002")));

		// when / then
		assertThatThrownBy(() -> readingService.getReadings(USER, SITE, null, null, ReadingStep.FIFTEEN_MINUTES))
			.isInstanceOf(TelemetrySiteNotFoundException.class);
		assertThatThrownBy(() -> readingService.getLatest(USER, SITE))
			.isInstanceOf(TelemetrySiteNotFoundException.class);
		assertThatThrownBy(() -> readingService.getSummary(USER, SITE, null, null))
			.isInstanceOf(TelemetrySiteNotFoundException.class);
		verifyNoInteractions(readingRepository);
	}

	@Test
	void shouldReturnLatestReadingWithItsAge() {
		// given
		givenVisible();
		Instant ts = Instant.parse("2026-10-26T10:06:00Z");
		when(readingRepository.findLatest(SITE)).thenReturn(Optional.of(new ReadingRow(SITE, ts, "current", null,
				118.2, "previous_value", 229.5, 10.1, 0.92, null, 41.0, List.of("consumption_sensor_failure"),
				"degraded")));

		// when
		Optional<LatestReadingResponse> latest = readingService.getLatest(USER, SITE);

		// then
		assertThat(latest).hasValueSatisfying(reading -> {
			assertThat(reading.ageSeconds()).isEqualTo(90);
			assertThat(reading.consumptionKw()).isNull();
			assertThat(reading.consumptionKwImputed()).isEqualTo(118.2);
			assertThat(reading.imputationMethod()).isEqualTo("previous_value");
		});
	}

	@Test
	void shouldReturnEmpty_whenSiteHasNoReading() {
		// given
		givenVisible();
		when(readingRepository.findLatest(SITE)).thenReturn(Optional.empty());

		// when / then
		assertThat(readingService.getLatest(USER, SITE)).isEmpty();
	}

	@Test
	void shouldComputeAvailabilityOverElapsedMinutes_whenSummarizing() {
		// given
		givenVisible();
		Instant from = Instant.parse("2026-10-26T08:30:00Z");
		when(readingRepository.summarize(SITE, from, Instant.parse("2026-10-26T10:08:00Z")))
			.thenReturn(new SummaryRow(250.4, 2, 140.0, Instant.parse("2026-10-26T09:12:00Z"), 95, 90, 4));

		// when
		ReadingSummaryResponse summary = readingService.getSummary(USER, SITE, from, null);

		// then: 08:30 to 10:07 = 97 minutes over 3 started hours (08, 09, 10)
		assertThat(summary.minutesExpected()).isEqualTo(97);
		assertThat(summary.hoursExpected()).isEqualTo(3);
		assertThat(summary.availabilityPercent()).isEqualTo(92.8);
		assertThat(summary.energyKwh()).isEqualTo(250.4);
		assertThat(summary.peakAt()).isEqualTo(Instant.parse("2026-10-26T09:12:00Z"));
		assertThat(summary.minutesImputed()).isEqualTo(4);
	}

	@Test
	void shouldReturnNullAvailability_whenNoMinuteIsElapsed() {
		// given
		givenVisible();
		Instant from = NOW.plus(Duration.ofHours(1));
		when(readingRepository.summarize(eq(SITE), any(), any()))
			.thenReturn(new SummaryRow(null, 0, null, null, 0, 0, 0));

		// when
		ReadingSummaryResponse summary = readingService.getSummary(USER, SITE, from, from.plus(Duration.ofHours(1)));

		// then
		assertThat(summary.minutesExpected()).isZero();
		assertThat(summary.hoursExpected()).isZero();
		assertThat(summary.availabilityPercent()).isNull();
	}

	@Test
	void shouldAlignOnUtcSteps() {
		Instant instant = Instant.parse("2026-10-26T10:07:30Z");
		assertThat(DefaultReadingService.floor(instant, Duration.ofMinutes(15)))
			.isEqualTo(Instant.parse("2026-10-26T10:00:00Z"));
		assertThat(DefaultReadingService.ceil(instant, Duration.ofMinutes(15)))
			.isEqualTo(Instant.parse("2026-10-26T10:15:00Z"));
		assertThat(DefaultReadingService.ceil(Instant.parse("2026-10-26T10:15:00Z"), Duration.ofMinutes(15)))
			.isEqualTo(Instant.parse("2026-10-26T10:15:00Z"));
	}

	private void givenVisible() {
		when(siteService.getSites(USER)).thenReturn(List.of(site("SITE002"), site(SITE)));
	}

	private static SiteSummaryResponse site(String siteId) {
		return new SiteSummaryResponse(siteId, "Site " + siteId, "office", "Paris", 200, "active");
	}

	private static BucketRow bucket(Instant ts) {
		return new BucketRow(ts, 120.5, 121.0, 230.0, 10.0, 0.915, 21.0, 40.0, 2, 15, 0, 1, List.of("linear"),
				List.of("electrical_sensor_failure"));
	}

}
