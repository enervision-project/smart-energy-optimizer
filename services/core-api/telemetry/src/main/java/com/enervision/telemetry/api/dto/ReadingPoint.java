package com.enervision.telemetry.api.dto;

import org.jspecify.annotations.Nullable;

import java.time.Instant;
import java.util.List;

/**
 * One step of a reading series. A step without any reading is still returned, with {@code null} values, so that
 * the chart shows the gap.
 *
 * @param ts                   start of the step (UTC)
 * @param consumptionKw        average of the raw values; {@code null} when none is available
 * @param consumptionKwImputed average of the raw values completed by the imputed ones (dashed line)
 * @param dataQuality          worst quality of the step ({@code good} &lt; {@code partial} &lt; {@code degraded}
 *                             &lt; {@code critical}); {@code null} without any reading
 * @param nullReasons          every {@code null_reasons} value seen in the step
 * @param minutesExpected      minutes of the step already elapsed: a step in progress is not reported incomplete
 * @param minutesReceived      minutes with a reading (raw values may be {@code null})
 * @param minutesWithConsumption minutes with a raw consumption: coverage of the measured curve
 * @param minutesBackfilled    readings recovered afterwards from the history endpoint
 * @param minutesImputed       readings whose consumption was imputed
 * @param imputationMethods    {@code previous_value}, {@code linear}
 */
public record ReadingPoint(
		Instant ts,
		@Nullable Double consumptionKw,
		@Nullable Double consumptionKwImputed,
		@Nullable Double voltageV,
		@Nullable Double currentA,
		@Nullable Double powerFactor,
		@Nullable Double temperatureCelsius,
		@Nullable Double humidityPercent,
		@Nullable String dataQuality,
		List<String> nullReasons,
		int minutesExpected,
		int minutesReceived,
		int minutesWithConsumption,
		int minutesBackfilled,
		int minutesImputed,
		List<String> imputationMethods) {
}
