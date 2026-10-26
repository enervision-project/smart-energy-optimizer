package com.enervision.telemetry.service.implementation;

import com.enervision.common.security.CurrentUser;
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
import com.enervision.telemetry.service.ReadingService;
import lombok.RequiredArgsConstructor;
import org.jspecify.annotations.Nullable;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.function.Function;
import java.util.stream.Collectors;

@Service
@RequiredArgsConstructor
@Transactional(readOnly = true)
class DefaultReadingService implements ReadingService {

	static final Duration DEFAULT_PERIOD = Duration.ofHours(48);
	static final Duration MAX_SUMMARY_PERIOD = Duration.ofDays(366);

	/** {@code worst_quality} index → code, from the best to the worst. */
	private static final List<String> QUALITIES = List.of("good", "partial", "degraded", "critical");

	private static final Duration MINUTE = Duration.ofMinutes(1);
	private static final Duration HOUR = Duration.ofHours(1);

	private final ReadingRepository readingRepository;
	private final SiteService siteService;
	private final Clock clock;

	@Override
	public ReadingSeriesResponse getReadings(CurrentUser user, String siteId, @Nullable Instant from,
			@Nullable Instant to, ReadingStep step) {
		requireVisible(user, siteId);
		Instant now = clock.instant();
		Duration width = step.duration();
		Instant end = ceil(to != null ? to : now, width);
		Instant start = floor(from != null ? from : end.minus(DEFAULT_PERIOD), width);
		checkPeriod(start, end, step.maxPeriod());

		Map<Instant, BucketRow> rows = readingRepository.findBuckets(siteId, width, start, end).stream()
			.collect(Collectors.toMap(BucketRow::bucket, Function.identity()));
		Instant elapsedUntil = now.truncatedTo(ChronoUnit.MINUTES);
		List<ReadingPoint> points = new ArrayList<>();
		for (Instant ts = start; ts.isBefore(end); ts = ts.plus(width)) {
			int expected = minutesBetween(ts, min(ts.plus(width), elapsedUntil));
			BucketRow row = rows.get(ts);
			points.add(row == null ? emptyPoint(ts, expected) : point(row, expected));
		}
		return new ReadingSeriesResponse(siteId, step.code(), start, end, points);
	}

	@Override
	public Optional<LatestReadingResponse> getLatest(CurrentUser user, String siteId) {
		requireVisible(user, siteId);
		Instant now = clock.instant();
		return readingRepository.findLatest(siteId).map(row -> latest(row, now));
	}

	@Override
	public ReadingSummaryResponse getSummary(CurrentUser user, String siteId, @Nullable Instant from,
			@Nullable Instant to) {
		requireVisible(user, siteId);
		Instant now = clock.instant();
		Instant end = ceil(to != null ? to : now, MINUTE);
		Instant start = floor(from != null ? from : end.minus(DEFAULT_PERIOD), MINUTE);
		checkPeriod(start, end, MAX_SUMMARY_PERIOD);

		SummaryRow row = readingRepository.summarize(siteId, start, end);
		Instant elapsedEnd = min(end, now.truncatedTo(ChronoUnit.MINUTES));
		int minutesExpected = minutesBetween(start, elapsedEnd);
		int hoursExpected = elapsedEnd.isAfter(start)
				? (int) Duration.between(floor(start, HOUR), ceil(elapsedEnd, HOUR)).toHours()
				: 0;
		Double availability = minutesExpected == 0
				? null
				: round(Math.min(100.0, 100.0 * row.minutesWithConsumption() / minutesExpected), 1);
		return new ReadingSummaryResponse(siteId, start, end, row.energyKwh(), row.hoursWithData(), hoursExpected,
				row.peakKw(), row.peakAt(), availability, minutesExpected, row.minutesReceived(),
				row.minutesWithConsumption(), row.minutesImputed());
	}

	/** From the visible sites rather than {@code canView}, which accepts any id for an admin. */
	private void requireVisible(CurrentUser user, String siteId) {
		if (siteService.getSites(user).stream().noneMatch(site -> site.siteId().equals(siteId))) {
			throw new TelemetrySiteNotFoundException(siteId);
		}
	}

	private static void checkPeriod(Instant start, Instant end, Duration max) {
		if (!start.isBefore(end)) {
			throw InvalidReadingPeriodException.empty(start, end);
		}
		if (Duration.between(start, end).compareTo(max) > 0) {
			throw InvalidReadingPeriodException.tooLong(start, end, max);
		}
	}

	private static ReadingPoint point(BucketRow row, int minutesExpected) {
		return new ReadingPoint(row.bucket(), row.consumptionKw(), row.consumptionKwImputed(), row.voltageV(),
				row.currentA(), row.powerFactor(), row.temperatureCelsius(), row.humidityPercent(),
				QUALITIES.get(Math.clamp(row.worstQuality(), 0, QUALITIES.size() - 1)), row.nullReasons(),
				minutesExpected, row.minutesReceived(), row.minutesBackfilled(), row.minutesImputed(),
				row.imputationMethods());
	}

	private static ReadingPoint emptyPoint(Instant ts, int minutesExpected) {
		return new ReadingPoint(ts, null, null, null, null, null, null, null, null, List.of(), minutesExpected, 0,
				0, 0, List.of());
	}

	private static LatestReadingResponse latest(ReadingRow row, Instant now) {
		return new LatestReadingResponse(row.siteId(), row.ts(), Math.max(0, Duration.between(row.ts(), now)
			.toSeconds()), row.source(), row.consumptionKw(), row.consumptionKwImputed(), row.imputationMethod(),
				row.voltageV(), row.currentA(), row.powerFactor(), row.temperatureCelsius(), row.humidityPercent(),
				row.nullReasons(), row.dataQuality());
	}

	/** Start of the UTC step holding {@code instant} (steps divide an hour, so they align on the epoch). */
	static Instant floor(Instant instant, Duration step) {
		long seconds = step.toSeconds();
		return Instant.ofEpochSecond(Math.floorDiv(instant.getEpochSecond(), seconds) * seconds);
	}

	/** {@code instant} itself when on a step boundary, else the start of the next step. */
	static Instant ceil(Instant instant, Duration step) {
		Instant floor = floor(instant, step);
		return floor.equals(instant) ? floor : floor.plus(step);
	}

	private static Instant min(Instant a, Instant b) {
		return a.isBefore(b) ? a : b;
	}

	private static int minutesBetween(Instant start, Instant end) {
		return end.isAfter(start) ? (int) Duration.between(start, end).toMinutes() : 0;
	}

	static double round(double value, int scale) {
		return BigDecimal.valueOf(value).setScale(scale, RoundingMode.HALF_UP).doubleValue();
	}

}
