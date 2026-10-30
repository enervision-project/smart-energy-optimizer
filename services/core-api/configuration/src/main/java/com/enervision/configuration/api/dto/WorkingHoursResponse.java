package com.enervision.configuration.api.dto;

/** Activity range in hours, {@code [start, end[}: {@code 0} to {@code 24} for a site active around the clock. */
public record WorkingHoursResponse(int start, int end) {
}
