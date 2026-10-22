package com.enervision.diagnostic.config;

import com.enervision.diagnostic.entity.AlertSeverity;
import com.enervision.diagnostic.entity.AlertType;
import org.springframework.context.annotation.Configuration;
import org.springframework.format.FormatterRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

/**
 * Binds the lowercase codes of the query string ({@code ?severity=high}) to the alert enums.
 * An unknown code is rejected with a 400.
 */
@Configuration
public class AlertWebConfig implements WebMvcConfigurer {

	@Override
	public void addFormatters(FormatterRegistry registry) {
		registry.addConverter(String.class, AlertSeverity.class, AlertSeverity::fromCode);
		registry.addConverter(String.class, AlertType.class, AlertType::fromCode);
	}

}
