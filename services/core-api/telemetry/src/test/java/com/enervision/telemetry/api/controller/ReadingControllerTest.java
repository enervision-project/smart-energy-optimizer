package com.enervision.telemetry.api.controller;

import com.enervision.common.security.CurrentUser;
import com.enervision.common.security.CurrentUserWebConfig;
import com.enervision.common.security.Role;
import com.enervision.telemetry.api.dto.LatestReadingResponse;
import com.enervision.telemetry.api.dto.ReadingPoint;
import com.enervision.telemetry.api.dto.ReadingSeriesResponse;
import com.enervision.telemetry.api.dto.ReadingStep;
import com.enervision.telemetry.api.dto.ReadingSummaryResponse;
import com.enervision.telemetry.exception.InvalidReadingPeriodException;
import com.enervision.telemetry.exception.TelemetrySiteNotFoundException;
import com.enervision.telemetry.service.ReadingService;
import org.hamcrest.Matchers;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.webmvc.test.autoconfigure.WebMvcTest;
import org.springframework.context.annotation.Import;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import java.time.Instant;
import java.util.List;
import java.util.Optional;
import java.util.UUID;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(ReadingController.class)
@Import(CurrentUserWebConfig.class)
class ReadingControllerTest {

	/** Authentication name = JWT subject = user id. */
	private static final String USER_ID = "3f2c8a1e-7b4d-4c1a-9e2f-5a6b7c8d9e0f";
	private static final CurrentUser USER = new CurrentUser(UUID.fromString(USER_ID), Role.USER);
	private static final Instant FROM = Instant.parse("2026-10-26T08:00:00Z");
	private static final Instant TO = Instant.parse("2026-10-26T09:00:00Z");

	@Autowired
	private MockMvc mockMvc;

	@MockitoBean
	private ReadingService readingService;

	@Test
	void shouldReturn401_whenNotAuthenticated() throws Exception {
		mockMvc.perform(get("/api/v1/sites/SITE001/readings"))
			.andExpect(status().isUnauthorized());
	}

	@Test
	@WithMockUser(username = USER_ID)
	void shouldReturnSeriesInCamelCase_withFifteenMinuteStepByDefault() throws Exception {
		// given
		ReadingPoint point = new ReadingPoint(FROM, 120.5, 121.0, 230.0, 10.0, 0.915, null, 40.0, "partial",
				List.of("temperature_sensor_failure"), 15, 15, 14, 0, 1, List.of("linear"));
		when(readingService.getReadings(USER, "SITE001", null, null, ReadingStep.FIFTEEN_MINUTES))
			.thenReturn(new ReadingSeriesResponse("SITE001", "15m", FROM, TO, List.of(point)));

		// when / then
		mockMvc.perform(get("/api/v1/sites/SITE001/readings"))
			.andExpect(status().isOk())
			.andExpect(jsonPath("$.step").value("15m"))
			.andExpect(jsonPath("$.from").value("2026-10-26T08:00:00Z"))
			.andExpect(jsonPath("$.points[0].consumptionKwImputed").value(121.0))
			.andExpect(jsonPath("$.points[0].temperatureCelsius").doesNotExist())
			.andExpect(jsonPath("$.points[0].nullReasons[0]").value("temperature_sensor_failure"))
			.andExpect(jsonPath("$.points[0].minutesWithConsumption").value(14))
			.andExpect(jsonPath("$.points[0].minutesImputed").value(1));
	}

	@Test
	@WithMockUser(username = USER_ID)
	void shouldBindPeriodAndStep() throws Exception {
		// given
		when(readingService.getReadings(USER, "SITE001", FROM, TO, ReadingStep.ONE_MINUTE))
			.thenReturn(new ReadingSeriesResponse("SITE001", "1m", FROM, TO, List.of()));

		// when / then
		mockMvc.perform(get("/api/v1/sites/SITE001/readings")
			.param("from", "2026-10-26T08:00:00Z")
			.param("to", "2026-10-26T09:00:00Z")
			.param("step", "1m"))
			.andExpect(status().isOk())
			.andExpect(jsonPath("$.step").value("1m"));
	}

	@Test
	@WithMockUser(username = USER_ID)
	void shouldReturn400_whenStepIsUnknown() throws Exception {
		mockMvc.perform(get("/api/v1/sites/SITE001/readings").param("step", "5m"))
			.andExpect(status().isBadRequest());
		verifyNoInteractions(readingService);
	}

	@Test
	@WithMockUser(username = USER_ID)
	void shouldReturn400_whenPeriodIsInvalid() throws Exception {
		// given
		when(readingService.getReadings(any(), any(), any(), any(), any()))
			.thenThrow(InvalidReadingPeriodException.empty(TO, FROM));

		// when / then
		mockMvc.perform(get("/api/v1/sites/SITE001/readings"))
			.andExpect(status().isBadRequest())
			.andExpect(jsonPath("$.detail").value(Matchers.containsString("Invalid period")));
	}

	@Test
	@WithMockUser(username = USER_ID)
	void shouldReturn404_whenSiteIsNotVisible() throws Exception {
		// given
		when(readingService.getLatest(USER, "SITE009")).thenThrow(new TelemetrySiteNotFoundException("SITE009"));

		// when / then
		mockMvc.perform(get("/api/v1/sites/SITE009/readings/latest"))
			.andExpect(status().isNotFound())
			.andExpect(jsonPath("$.detail").value("Site SITE009 not found"));
	}

	@Test
	@WithMockUser(username = USER_ID)
	void shouldReturnLatestReading() throws Exception {
		// given
		when(readingService.getLatest(USER, "SITE001")).thenReturn(Optional.of(new LatestReadingResponse("SITE001",
				TO, 42, "current", 87.3, null, null, 230.0, 10.0, 0.9, 21.0, 40.0, List.of(), "good")));

		// when / then
		mockMvc.perform(get("/api/v1/sites/SITE001/readings/latest"))
			.andExpect(status().isOk())
			.andExpect(jsonPath("$.ageSeconds").value(42))
			.andExpect(jsonPath("$.source").value("current"))
			.andExpect(jsonPath("$.consumptionKw").value(87.3));
	}

	@Test
	@WithMockUser(username = USER_ID)
	void shouldReturn204_whenSiteHasNoReading() throws Exception {
		// given
		when(readingService.getLatest(USER, "SITE001")).thenReturn(Optional.empty());

		// when / then
		mockMvc.perform(get("/api/v1/sites/SITE001/readings/latest"))
			.andExpect(status().isNoContent());
	}

	@Test
	@WithMockUser(username = USER_ID)
	void shouldReturnSummary() throws Exception {
		// given
		when(readingService.getSummary(USER, "SITE001", FROM, null)).thenReturn(new ReadingSummaryResponse(
				"SITE001", FROM, TO, 120.4, 1, 1, 140.0, FROM, 95.0, 60, 58, 57, 2));

		// when / then
		mockMvc.perform(get("/api/v1/sites/SITE001/readings/summary").param("from", "2026-10-26T08:00:00Z"))
			.andExpect(status().isOk())
			.andExpect(jsonPath("$.energyKwh").value(120.4))
			.andExpect(jsonPath("$.availabilityPercent").value(95.0))
			.andExpect(jsonPath("$.minutesImputed").value(2));
	}

}
