package com.enervision.telemetry.config;

import com.enervision.telemetry.api.dto.ReadingStep;
import org.springframework.context.annotation.Configuration;
import org.springframework.format.FormatterRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class TelemetryWebConfig implements WebMvcConfigurer {

	@Override
	public void addFormatters(FormatterRegistry registry) {
		registry.addConverter(String.class, ReadingStep.class, ReadingStep::fromCode);
	}

}
