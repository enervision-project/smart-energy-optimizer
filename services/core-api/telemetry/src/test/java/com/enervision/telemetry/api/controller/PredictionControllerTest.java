package com.enervision.telemetry.api.controller;

import com.enervision.common.security.CurrentUser;
import com.enervision.common.security.CurrentUserWebConfig;
import com.enervision.common.security.Role;
import com.enervision.telemetry.api.dto.PredictionPointResponse;
import com.enervision.telemetry.api.dto.PredictionSeriesResponse;
import com.enervision.telemetry.exception.InvalidPredictionPeriodException;
import com.enervision.telemetry.exception.TelemetrySiteNotFoundException;
import com.enervision.telemetry.service.PredictionService;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.webmvc.test.autoconfigure.WebMvcTest;
import org.springframework.context.annotation.Import;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;
import java.util.UUID;

import static org.hamcrest.Matchers.containsString;
import static org.hamcrest.Matchers.nullValue;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(PredictionController.class)
@Import(CurrentUserWebConfig.class)
class PredictionControllerTest {

	private static final String USER_ID = "3f2c8a1e-7b4d-4c1a-9e2f-5a6b7c8d9e0f";
	private static final CurrentUser USER = new CurrentUser(UUID.fromString(USER_ID), Role.USER);
	private static final Instant FROM = Instant.parse("2026-10-26T08:00:00Z");
	private static final Instant TO = Instant.parse("2026-10-26T10:00:00Z");
	private static final UUID RUN_ID = UUID.fromString("00000000-0000-0000-0000-000000000003");
	private static final String ROUTE = "/api/v1/sites/SITE001/predictions";

	@Autowired
	private MockMvc mockMvc;

	@MockitoBean
	private PredictionService predictionService;

	@Test
	void shouldReturn401_whenNotAuthenticated() throws Exception {
		mockMvc.perform(get(ROUTE)).andExpect(status().isUnauthorized());
		verifyNoInteractions(predictionService);
	}

	@Test
	@WithMockUser(username = USER_ID)
	void shouldReturnHourlyEnergyAndMetadataInCamelCase_includingNullGaps() throws Exception {
		// given
		PredictionPointResponse point = new PredictionPointResponse(FROM, new BigDecimal("123.456"), RUN_ID,
				"hourly-consumption", "3", FROM.minusSeconds(3600));
		PredictionPointResponse gap = new PredictionPointResponse(FROM.plusSeconds(3600), null, null, null, null, null);
		when(predictionService.getPredictions(USER, "SITE001", null, null))
			.thenReturn(new PredictionSeriesResponse("SITE001", "1h", FROM, TO, List.of(point, gap)));

		// when / then
		mockMvc.perform(get(ROUTE))
			.andExpect(status().isOk())
			.andExpect(jsonPath("$.siteId").value("SITE001"))
			.andExpect(jsonPath("$.step").value("1h"))
			.andExpect(jsonPath("$.from").value(FROM.toString()))
			.andExpect(jsonPath("$.to").value(TO.toString()))
			.andExpect(jsonPath("$.points[0].ts").value(FROM.toString()))
			.andExpect(jsonPath("$.points[0].predictionKwh").value(123.456))
			.andExpect(jsonPath("$.points[0].runId").value(RUN_ID.toString()))
			.andExpect(jsonPath("$.points[0].modelName").value("hourly-consumption"))
			.andExpect(jsonPath("$.points[0].modelVersion").value("3"))
			.andExpect(jsonPath("$.points[0].generatedAt").value(FROM.minusSeconds(3600).toString()))
			.andExpect(jsonPath("$.points[1].predictionKwh").value(nullValue()))
			.andExpect(jsonPath("$.points[1].runId").value(nullValue()));
	}

	@Test
	@WithMockUser(username = USER_ID)
	void shouldBindExplicitUtcBounds() throws Exception {
		when(predictionService.getPredictions(USER, "SITE001", FROM, TO))
			.thenReturn(new PredictionSeriesResponse("SITE001", "1h", FROM, TO, List.of()));
		mockMvc.perform(get(ROUTE).param("from", FROM.toString()).param("to", TO.toString()))
			.andExpect(status().isOk()).andExpect(jsonPath("$.step").value("1h"));
	}

	@Test
	@WithMockUser(username = USER_ID)
	void shouldConvertExplicitOffsetsToInstants() throws Exception {
		when(predictionService.getPredictions(USER, "SITE001", FROM, TO))
			.thenReturn(new PredictionSeriesResponse("SITE001", "1h", FROM, TO, List.of()));
		mockMvc.perform(get(ROUTE)
			.param("from", "2026-10-26T09:00:00+01:00")
			.param("to", "2026-10-26T11:00:00+01:00"))
			.andExpect(status().isOk()).andExpect(jsonPath("$.from").value(FROM.toString()));
	}

	@Test
	@WithMockUser(username = USER_ID)
	void shouldReturn400_withoutCallingTheService_whenDateIsMalformed() throws Exception {
		mockMvc.perform(get(ROUTE).param("from", "not-a-date")).andExpect(status().isBadRequest());
		verifyNoInteractions(predictionService);
	}

	@Test
	@WithMockUser(username = USER_ID)
	void shouldReturnProblemDetail_whenPeriodIsInvalid() throws Exception {
		when(predictionService.getPredictions(USER, "SITE001", TO, FROM))
			.thenThrow(InvalidPredictionPeriodException.empty(TO, FROM));
		mockMvc.perform(get(ROUTE).param("from", TO.toString()).param("to", FROM.toString()))
			.andExpect(status().isBadRequest())
			.andExpect(content().contentTypeCompatibleWith("application/problem+json"))
			.andExpect(jsonPath("$.detail").value(containsString("Invalid period")));
	}

	@Test
	@WithMockUser(username = USER_ID)
	void shouldReturn404_whenSiteIsUnknownOrInaccessible() throws Exception {
		when(predictionService.getPredictions(USER, "SITE001", null, null))
			.thenThrow(new TelemetrySiteNotFoundException("SITE001"));
		mockMvc.perform(get(ROUTE))
			.andExpect(status().isNotFound())
			.andExpect(jsonPath("$.detail").value("Site SITE001 not found"));
	}

}
