package com.enervision.telemetry.service;

import com.enervision.common.security.CurrentUser;
import com.enervision.telemetry.api.dto.ParkSummaryResponse;

/**
 * Current consumption of the sites visible to the user.
 */
public interface ParkService {

	ParkSummaryResponse getSummary(CurrentUser user);

}
