package com.enervision.configuration.api.dto;

import org.jspecify.annotations.Nullable;

import java.math.BigDecimal;
import java.time.DayOfWeek;
import java.util.List;

/** Consumptions in kW; ratios such as 0.15 for ±15 %; {@code weekendFactor} is {@code null} when the site has none. */
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
