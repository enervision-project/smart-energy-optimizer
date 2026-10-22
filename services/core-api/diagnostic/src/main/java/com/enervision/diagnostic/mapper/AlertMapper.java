package com.enervision.diagnostic.mapper;

import com.enervision.diagnostic.api.dto.AlertResponse;
import com.enervision.diagnostic.entity.Alert;
import org.springframework.stereotype.Component;

@Component
public class AlertMapper {

	public AlertResponse toResponse(Alert alert, String siteName, boolean recent) {
		return new AlertResponse(
				alert.getAlertId(),
				alert.getSiteId(),
				siteName,
				alert.getTimestamp(),
				alert.getSeverity(),
				alert.getType(),
				alert.getMessage(),
				alert.getValue(),
				alert.getThreshold(),
				recent);
	}

}
