package com.enervision.telemetry.service.implementation;

import com.enervision.common.security.CurrentUser;
import com.enervision.configuration.api.dto.SiteSummaryResponse;
import com.enervision.configuration.service.SiteService;
import com.enervision.telemetry.api.dto.ParkSummaryResponse;
import com.enervision.telemetry.api.dto.SiteLoadResponse;
import com.enervision.telemetry.repository.ReadingRepository;
import com.enervision.telemetry.repository.ReadingRow;
import com.enervision.telemetry.service.ParkService;
import lombok.RequiredArgsConstructor;
import org.jspecify.annotations.Nullable;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;

import static com.enervision.telemetry.service.implementation.DefaultReadingService.round;

@Service
@RequiredArgsConstructor
@Transactional(readOnly = true)
class DefaultParkService implements ParkService {

	/** A reading older than this is not "current": the site is reported without data. */
	static final Duration FRESHNESS = Duration.ofMinutes(3);

	private final ReadingRepository readingRepository;
	private final SiteService siteService;
	private final Clock clock;

	@Override
	public ParkSummaryResponse getSummary(CurrentUser user) {
		List<SiteSummaryResponse> sites = siteService.getSites(user).stream()
			.sorted(Comparator.comparing(SiteSummaryResponse::siteId))
			.toList();
		Instant now = clock.instant();
		Map<String, ReadingRow> latest = sites.isEmpty()
				? Map.of()
				: readingRepository.findLatestPerSite(sites.stream().map(SiteSummaryResponse::siteId).toList(),
						now.minus(FRESHNESS))
					.stream()
					.collect(Collectors.toMap(ReadingRow::siteId, Function.identity()));

		double totalConsumption = 0;
		double totalCapacity = 0;
		List<String> withoutData = new ArrayList<>();
		List<SiteLoadResponse> loads = new ArrayList<>();
		for (SiteSummaryResponse site : sites) {
			ReadingRow row = latest.get(site.siteId());
			SiteLoadResponse load = load(site, row, now);
			totalCapacity += site.capacityKw();
			if (load.currentConsumptionKw() == null) {
				withoutData.add(site.siteId());
			} else {
				totalConsumption += load.currentConsumptionKw();
			}
			loads.add(load);
		}
		Double averageLoad = totalCapacity > 0 ? round(100 * totalConsumption / totalCapacity, 1) : null;
		return new ParkSummaryResponse(now, sites.size(), round(totalConsumption, 2), totalCapacity, averageLoad,
				withoutData, loads);
	}

	/** Raw value first; the imputed one only when the sensor failed (it is then flagged as an estimate). */
	private static SiteLoadResponse load(SiteSummaryResponse site, @Nullable ReadingRow row, Instant now) {
		if (row == null) {
			return new SiteLoadResponse(site.siteId(), site.siteName(), null, false, site.capacityKw(), null, null,
					null, null);
		}
		Double consumption = row.consumptionKw() != null ? row.consumptionKw() : row.consumptionKwImputed();
		boolean imputed = row.consumptionKw() == null && consumption != null;
		Double loadPercent = consumption == null || site.capacityKw() <= 0
				? null
				: round(100 * consumption / site.capacityKw(), 1);
		return new SiteLoadResponse(site.siteId(), site.siteName(), consumption, imputed, site.capacityKw(),
				loadPercent, row.dataQuality(), row.ts(), Math.max(0, Duration.between(row.ts(), now).toSeconds()));
	}

}
