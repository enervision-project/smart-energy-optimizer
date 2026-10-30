package com.enervision.telemetry.service;

import com.enervision.common.security.CurrentUser;
import com.enervision.telemetry.api.dto.ParkSummaryResponse;

public interface ParkService {

	ParkSummaryResponse getSummary(CurrentUser user);

}
