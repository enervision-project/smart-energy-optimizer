package com.enervision.telemetry.config;

import com.enervision.telemetry.api.dto.ReadingStep;
import org.springframework.context.annotation.Configuration;
import org.springframework.format.FormatterRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

/**
 * Binds the step code of the query string ({@code ?step=15m}) to {@link ReadingStep}. An unknown code is rejected
 * with a 400.
 */
@Configuration
public class TelemetryWebConfig implements WebMvcConfigurer {

	@Override
	public void addFormatters(FormatterRegistry registry) {
		registry.addConverter(String.class, ReadingStep.class, ReadingStep::fromCode);
	}

}
