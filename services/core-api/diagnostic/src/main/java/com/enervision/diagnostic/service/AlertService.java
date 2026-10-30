package com.enervision.diagnostic.service;

import com.enervision.common.security.CurrentUser;
import com.enervision.diagnostic.api.dto.AlertResponse;
import com.enervision.diagnostic.api.dto.AlertSearchRequest;
import com.enervision.diagnostic.api.dto.AlertSummaryResponse;
import org.jspecify.annotations.Nullable;
import org.springframework.data.domain.Page;

/** Alerts are a random sample of the energy API with no lifecycle: "recent" means under an hour old. */
public interface AlertService {

	/** Alerts matching the filters, newest first; a site the user cannot see is reported as not found. */
	Page<AlertResponse> getAlerts(CurrentUser user, AlertSearchRequest request, int page, int size);

	/** Recent alerts count per severity, for every visible site or for {@code siteId} only. */
	AlertSummaryResponse getSummary(CurrentUser user, @Nullable String siteId);

}
