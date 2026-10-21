package com.enervision.configuration.mapper;

import com.enervision.configuration.api.dto.SiteProfileResponse;
import com.enervision.configuration.api.dto.SiteResponse;
import com.enervision.configuration.api.dto.SiteSummaryResponse;
import com.enervision.configuration.api.dto.WorkingHoursResponse;
import com.enervision.configuration.entity.Site;
import com.enervision.configuration.entity.SiteProfile;
import org.jspecify.annotations.Nullable;
import org.springframework.stereotype.Component;

import java.time.DayOfWeek;
import java.util.Arrays;
import java.util.List;

@Component
public class SiteMapper {

	public SiteSummaryResponse toSummaryResponse(Site site) {
		return new SiteSummaryResponse(
				site.getSiteId(),
				site.getSiteName(),
				site.getSiteType(),
				site.getLocation(),
				site.getCapacityKw(),
				site.getStatus());
	}

	public SiteResponse toResponse(Site site, @Nullable SiteProfile profile) {
		return new SiteResponse(
				site.getSiteId(),
				site.getSiteName(),
				site.getSiteType(),
				site.getLocation(),
				site.getCapacityKw(),
				site.getStatus(),
				site.getUpdatedAt(),
				profile == null ? null : toProfileResponse(profile));
	}

	private SiteProfileResponse toProfileResponse(SiteProfile profile) {
		return new SiteProfileResponse(
				profile.getBaseConsumption(),
				profile.getPeakConsumption(),
				new WorkingHoursResponse(profile.getWorkingHourStart(), profile.getWorkingHourEnd()),
				toDaysOfWeek(profile.getWorkingDays()),
				profile.getSeasonalVariation(),
				profile.getNoiseLevel(),
				profile.getWeekendFactor(),
				profile.isShiftPattern());
	}

	/** ISO numbers stored in the database (1 = Monday … 7 = Sunday), same numbering as {@link DayOfWeek#of(int)}. */
	private static List<DayOfWeek> toDaysOfWeek(Short[] isoDays) {
		return Arrays.stream(isoDays)
			.map(DayOfWeek::of)
			.distinct()
			.sorted()
			.toList();
	}

}
