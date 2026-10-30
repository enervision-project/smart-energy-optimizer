package com.enervision.diagnostic.config;

import com.enervision.diagnostic.entity.AlertSeverity;
import com.enervision.diagnostic.entity.AlertType;
import org.springframework.context.annotation.Configuration;
import org.springframework.format.FormatterRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

/** Binds lowercase query codes ({@code ?severity=high}) to the enums; an unknown code gives a 400. */
@Configuration
public class AlertWebConfig implements WebMvcConfigurer {

	@Override
	public void addFormatters(FormatterRegistry registry) {
		registry.addConverter(String.class, AlertSeverity.class, AlertSeverity::fromCode);
		registry.addConverter(String.class, AlertType.class, AlertType::fromCode);
	}

}
