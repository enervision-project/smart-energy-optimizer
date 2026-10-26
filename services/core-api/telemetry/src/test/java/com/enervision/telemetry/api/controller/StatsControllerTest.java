package com.enervision.telemetry.api.controller;

import com.enervision.common.security.CurrentUser;
import com.enervision.common.security.CurrentUserWebConfig;
import com.enervision.common.security.Role;
import com.enervision.telemetry.api.dto.ParkSummaryResponse;
import com.enervision.telemetry.api.dto.SiteLoadResponse;
import com.enervision.telemetry.service.ParkService;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.webmvc.test.autoconfigure.WebMvcTest;
import org.springframework.context.annotation.Import;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import java.time.Instant;
import java.util.List;
import java.util.UUID;

import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(StatsController.class)
@Import(CurrentUserWebConfig.class)
class StatsControllerTest {

	private static final String USER_ID = "3f2c8a1e-7b4d-4c1a-9e2f-5a6b7c8d9e0f";
	private static final CurrentUser USER = new CurrentUser(UUID.fromString(USER_ID), Role.USER);

	@Autowired
	private MockMvc mockMvc;

	@MockitoBean
	private ParkService parkService;

	@Test
	void shouldReturn401_whenNotAuthenticated() throws Exception {
		mockMvc.perform(get("/api/v1/stats/summary"))
			.andExpect(status().isUnauthorized());
	}

	@Test
	@WithMockUser(username = USER_ID)
	void shouldReturnParkSummaryInCamelCase() throws Exception {
		// given
		Instant now = Instant.parse("2026-10-26T10:07:30Z");
		when(parkService.getSummary(USER)).thenReturn(new ParkSummaryResponse(now, 2, 87.34, 1000, 8.7,
				List.of("SITE003"), List.of(
						new SiteLoadResponse("SITE001", "Bureau", 87.34, false, 200, 43.7, "good",
								Instant.parse("2026-10-26T10:07:00Z"), 30L),
						new SiteLoadResponse("SITE003", "Data center", null, false, 800, null, null, null, null))));

		// when / then
		mockMvc.perform(get("/api/v1/stats/summary"))
			.andExpect(status().isOk())
			.andExpect(jsonPath("$.totalConsumptionKw").value(87.34))
			.andExpect(jsonPath("$.averageLoadPercent").value(8.7))
			.andExpect(jsonPath("$.sitesWithoutData[0]").value("SITE003"))
			.andExpect(jsonPath("$.sites[0].loadPercent").value(43.7))
			.andExpect(jsonPath("$.sites[1].currentConsumptionKw").doesNotExist());
	}

}
