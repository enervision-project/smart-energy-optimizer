package com.enervision.telemetry.api.dto;

import org.jspecify.annotations.Nullable;

import java.time.Instant;

/**
 * Key figures of a site over {@code [from, to)}, computed from raw values only.
 *
 * @param energyKwh              sum of the hourly averages of the raw power; hours without any value are left out
 *                               and missing from {@code hoursWithData}
 * @param hoursExpected          hours of the period already started
 * @param peakKw                 highest raw power, at the minute
 * @param availabilityPercent    minutes with a raw consumption / minutes expected
 * @param minutesExpected        minutes of the period already elapsed
 * @param minutesReceived        minutes with a reading (raw values may be {@code null})
 * @param minutesWithConsumption minutes with a raw consumption
 * @param minutesImputed         minutes whose consumption was imputed
 */
public record ReadingSummaryResponse(
		String siteId,
		Instant from,
		Instant to,
		@Nullable Double energyKwh,
		int hoursWithData,
		int hoursExpected,
		@Nullable Double peakKw,
		@Nullable Instant peakAt,
		@Nullable Double availabilityPercent,
		int minutesExpected,
		int minutesReceived,
		int minutesWithConsumption,
		int minutesImputed) {
}
