package com.enervision.diagnostic.service.implementation;

import com.enervision.common.security.CurrentUser;
import com.enervision.configuration.api.dto.SiteSummaryResponse;
import com.enervision.configuration.service.SiteService;
import com.enervision.diagnostic.api.dto.AlertResponse;
import com.enervision.diagnostic.api.dto.AlertSearchRequest;
import com.enervision.diagnostic.api.dto.AlertSummaryResponse;
import com.enervision.diagnostic.entity.AlertSeverity;
import com.enervision.diagnostic.entity.AlertType;
import com.enervision.diagnostic.exception.AlertSiteNotFoundException;
import com.enervision.diagnostic.exception.InvalidAlertPeriodException;
import com.enervision.diagnostic.mapper.AlertMapper;
import com.enervision.diagnostic.repository.AlertRepository;
import com.enervision.diagnostic.repository.AlertSpecifications;
import com.enervision.diagnostic.repository.SeverityCount;
import com.enervision.diagnostic.service.AlertService;
import lombok.RequiredArgsConstructor;
import org.jspecify.annotations.Nullable;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.function.Function;
import java.util.stream.Collectors;

@Service
@RequiredArgsConstructor
@Transactional(readOnly = true)
class DefaultAlertService implements AlertService {

	/** Same window as the energy API, which dates its alerts within the hour before the call. */
	static final Duration RECENT_PERIOD = Duration.ofHours(1);

	/** Alert id as a tie-breaker: several alerts can share a timestamp, pages must stay stable. */
	private static final Sort NEWEST_FIRST = Sort.by(Sort.Order.desc("timestamp"), Sort.Order.asc("alertId"));

	private final AlertRepository alertRepository;
	private final SiteService siteService;
	private final AlertMapper alertMapper;
	private final Clock clock;

	@Override
	public Page<AlertResponse> getAlerts(CurrentUser user, AlertSearchRequest request, int page, int size) {
		Map<String, String> siteNames = visibleSiteNames(user, request.siteId());
		Instant now = clock.instant();
		Instant to = request.to() != null ? request.to() : now;
		Instant from = request.from() != null ? request.from() : to.minus(RECENT_PERIOD);
		if (from.isAfter(to)) {
			throw new InvalidAlertPeriodException(from, to);
		}
		Pageable pageable = PageRequest.of(page, size, NEWEST_FIRST);
		if (siteNames.isEmpty()) {
			return Page.empty(pageable);
		}

		Instant recentSince = now.minus(RECENT_PERIOD);
		return alertRepository.findAll(
				AlertSpecifications.matching(
						siteNames.keySet(),
						codes(request.severity(), AlertSeverity::code),
						codes(request.type(), AlertType::code),
						from,
						to),
				pageable)
			.map(alert -> alertMapper.toResponse(
					alert, siteNames.get(alert.getSiteId()), !alert.getTimestamp().isBefore(recentSince)));
	}

	@Override
	public AlertSummaryResponse getSummary(CurrentUser user, @Nullable String siteId) {
		Map<String, String> siteNames = visibleSiteNames(user, siteId);
		Instant since = clock.instant().minus(RECENT_PERIOD);

		Map<String, Long> bySeverity = new LinkedHashMap<>();
		for (AlertSeverity severity : AlertSeverity.values()) {
			bySeverity.put(severity.code(), 0L);
		}
		long total = 0;
		List<SeverityCount> counts = siteNames.isEmpty()
				? List.of()
				: alertRepository.countBySeveritySince(siteNames.keySet(), since);
		for (SeverityCount count : counts) {
			total += count.count();
			bySeverity.computeIfPresent(count.severity(), (severity, current) -> current + count.count());
		}
		return new AlertSummaryResponse(since, total, Collections.unmodifiableMap(bySeverity));
	}

	/** Visible sites by id, with their name; only {@code siteId} when given, which must be visible. */
	private Map<String, String> visibleSiteNames(CurrentUser user, @Nullable String siteId) {
		Map<String, String> siteNames = siteService.getSites(user).stream()
			.collect(Collectors.toMap(SiteSummaryResponse::siteId, SiteSummaryResponse::siteName));
		if (siteId == null) {
			return siteNames;
		}
		String siteName = siteNames.get(siteId);
		if (siteName == null) {
			throw new AlertSiteNotFoundException(siteId);
		}
		return Map.of(siteId, siteName);
	}

	private static <E> Set<String> codes(@Nullable Set<E> values, Function<E, String> code) {
		return values == null ? Set.of() : values.stream().map(code).collect(Collectors.toSet());
	}

}
