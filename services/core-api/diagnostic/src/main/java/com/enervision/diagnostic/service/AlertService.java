package com.enervision.diagnostic.service;

import com.enervision.common.security.CurrentUser;
import com.enervision.diagnostic.api.dto.AlertResponse;
import com.enervision.diagnostic.api.dto.AlertSearchRequest;
import com.enervision.diagnostic.api.dto.AlertSummaryResponse;
import org.jspecify.annotations.Nullable;
import org.springframework.data.domain.Page;

/**
 * Alerts of the sites visible to a user (see {@code SiteService}). Alerts are a random sample of the energy API
 * with no lifecycle: an alert is "recent" when it is less than an hour old.
 */
public interface AlertService {

	/** Alerts matching the filters, newest first; a site the user cannot see is reported as not found. */
	Page<AlertResponse> getAlerts(CurrentUser user, AlertSearchRequest request, int page, int size);

	/** Recent alerts count per severity, for every visible site or for {@code siteId} only. */
	AlertSummaryResponse getSummary(CurrentUser user, @Nullable String siteId);

}
