package com.enervision.diagnostic.api.dto;

import com.enervision.diagnostic.entity.AlertSeverity;
import com.enervision.diagnostic.entity.AlertType;
import org.jspecify.annotations.Nullable;

import java.time.Instant;
import java.util.Set;

/** Query string filters, all optional; {@code from} defaults to an hour before {@code to}, {@code to} to now. */
public record AlertSearchRequest(
		@Nullable String siteId,
		@Nullable Set<AlertSeverity> severity,
		@Nullable Set<AlertType> type,
		@Nullable Instant from,
		@Nullable Instant to) {
}
