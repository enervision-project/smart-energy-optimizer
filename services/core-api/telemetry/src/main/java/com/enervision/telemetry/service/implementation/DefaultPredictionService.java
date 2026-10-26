package com.enervision.telemetry.service.implementation;

import com.enervision.common.security.CurrentUser;
import com.enervision.configuration.service.SiteService;
import com.enervision.telemetry.api.dto.PredictionPointResponse;
import com.enervision.telemetry.api.dto.PredictionSeriesResponse;
import com.enervision.telemetry.entity.Prediction;
import com.enervision.telemetry.exception.InvalidPredictionPeriodException;
import com.enervision.telemetry.exception.TelemetrySiteNotFoundException;
import com.enervision.telemetry.mapper.PredictionMapper;
import com.enervision.telemetry.repository.PredictionRepository;
import com.enervision.telemetry.service.PredictionService;
import lombok.RequiredArgsConstructor;
import org.jspecify.annotations.Nullable;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;

@Service
@RequiredArgsConstructor
@Transactional(readOnly = true)
class DefaultPredictionService implements PredictionService {

	static final Duration DEFAULT_PERIOD = Duration.ofHours(24);
	static final Duration MAX_PERIOD = Duration.ofDays(366);

	private final PredictionRepository predictionRepository;
	private final SiteService siteService;
	private final PredictionMapper predictionMapper;
	private final Clock clock;

	@Override
	public PredictionSeriesResponse getPredictions(CurrentUser user, String siteId, @Nullable Instant from,
			@Nullable Instant to) {
		if (siteService.getSites(user).stream().noneMatch(site -> site.siteId().equals(siteId))) {
			throw new TelemetrySiteNotFoundException(siteId);
		}
		// Reject inverted bounds before alignment, including two instants within the same hour.
		if (from != null && to != null && !from.isBefore(to)) {
			throw InvalidPredictionPeriodException.empty(from, to);
		}
		Instant start;
		Instant end;
		if (from == null && to != null) {
			end = ceil(to);
			start = end.minus(DEFAULT_PERIOD);
		} else {
			start = (from != null ? from : clock.instant()).truncatedTo(ChronoUnit.HOURS);
			end = to != null ? ceil(to) : start.plus(DEFAULT_PERIOD);
		}
		if (Duration.between(start, end).compareTo(MAX_PERIOD) > 0) {
			throw InvalidPredictionPeriodException.tooLong(start, end, MAX_PERIOD);
		}

		Map<Instant, Prediction> predictions = predictionRepository.findLatestForSite(siteId, start, end).stream()
			.collect(Collectors.toMap(Prediction::getPredictedFor, Function.identity()));
		List<PredictionPointResponse> points = new ArrayList<>();
		for (Instant ts = start; ts.isBefore(end); ts = ts.plus(1, ChronoUnit.HOURS)) {
			Prediction prediction = predictions.get(ts);
			points.add(prediction == null
					? new PredictionPointResponse(ts, null, null, null, null, null)
					: predictionMapper.toResponse(prediction));
		}
		return new PredictionSeriesResponse(siteId, "1h", start, end, points);
	}

	private static Instant ceil(Instant instant) {
		Instant floor = instant.truncatedTo(ChronoUnit.HOURS);
		return floor.equals(instant) ? floor : floor.plus(1, ChronoUnit.HOURS);
	}

}
