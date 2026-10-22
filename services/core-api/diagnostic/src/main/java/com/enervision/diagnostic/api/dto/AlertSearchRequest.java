package com.enervision.diagnostic.api.dto;

import com.enervision.diagnostic.entity.AlertSeverity;
import com.enervision.diagnostic.entity.AlertType;
import org.jspecify.annotations.Nullable;

import java.time.Instant;
import java.util.Set;

/**
 * Alert search filters, bound from the query string. Every filter is optional.
 *
 * @param siteId   one site; every visible site when {@code null}
 * @param severity accepted severities; every severity when {@code null} or empty
 * @param type     accepted types; every type when {@code null} or empty
 * @param from     start of the period, included; an hour before {@code to} when {@code null}
 * @param to       end of the period, included; now when {@code null}
 */
public record AlertSearchRequest(
		@Nullable String siteId,
		@Nullable Set<AlertSeverity> severity,
		@Nullable Set<AlertType> type,
		@Nullable Instant from,
		@Nullable Instant to) {
}
