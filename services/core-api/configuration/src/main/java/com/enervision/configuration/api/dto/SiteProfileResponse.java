package com.enervision.configuration.api.dto;

import org.jspecify.annotations.Nullable;

import java.math.BigDecimal;
import java.time.DayOfWeek;
import java.util.List;

/**
 * @param baseConsumption   expected consumption at rest (kW)
 * @param peakConsumption   expected consumption peak during activity (kW)
 * @param workingDays       activity days, sorted from Monday to Sunday
 * @param seasonalVariation ratio, e.g. 0.15 for ±15 %
 * @param noiseLevel        ratio
 * @param weekendFactor     weekend consumption multiplier, e.g. 1.2 for +20 %; {@code null} when the site has none
 */
public record SiteProfileResponse(
		BigDecimal baseConsumption,
		BigDecimal peakConsumption,
		WorkingHoursResponse workingHours,
		List<DayOfWeek> workingDays,
		BigDecimal seasonalVariation,
		BigDecimal noiseLevel,
		@Nullable BigDecimal weekendFactor,
		boolean shiftPattern) {
}
