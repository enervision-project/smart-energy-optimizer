package com.enervision.diagnostic.api.controller;

import com.enervision.common.security.CurrentUser;
import com.enervision.common.security.CurrentUserWebConfig;
import com.enervision.common.security.Role;
import com.enervision.diagnostic.api.dto.AlertResponse;
import com.enervision.diagnostic.api.dto.AlertSearchRequest;
import com.enervision.diagnostic.api.dto.AlertSummaryResponse;
import com.enervision.diagnostic.entity.AlertSeverity;
import com.enervision.diagnostic.entity.AlertType;
import com.enervision.diagnostic.exception.AlertSiteNotFoundException;
import com.enervision.diagnostic.exception.InvalidAlertPeriodException;
import com.enervision.diagnostic.service.AlertService;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.webmvc.test.autoconfigure.WebMvcTest;
import org.springframework.context.annotation.Import;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageImpl;
import org.springframework.data.domain.PageRequest;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.UUID;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyInt;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(AlertController.class)
@Import(CurrentUserWebConfig.class)
class AlertControllerTest {

	/** Authentication name = JWT subject = user id. */
	private static final String USER_ID = "3f2c8a1e-7b4d-4c1a-9e2f-5a6b7c8d9e0f";
	private static final CurrentUser USER = new CurrentUser(UUID.fromString(USER_ID), Role.USER);

	@Autowired
	private MockMvc mockMvc;

	@MockitoBean
	private AlertService alertService;

	@Test
	void shouldReturn401_whenNotAuthenticated() throws Exception {
		mockMvc.perform(get("/api/v1/alerts"))
			.andExpect(status().isUnauthorized());
	}

	@Test
	@WithMockUser(username = USER_ID)
	void shouldReturnPagedAlertsInCamelCase_whenNoFilter() throws Exception {
		// given
		Page<AlertResponse> alerts = new PageImpl<>(List.of(alert()), PageRequest.of(0, 50), 1);
		when(alertService.getAlerts(USER, new AlertSearchRequest(null, null, null, null, null), 0, 50))
			.thenReturn(alerts);

		// when / then
		mockMvc.perform(get("/api/v1/alerts"))
			.andExpect(status().isOk())
			.andExpect(jsonPath("$.content[0].alertId").value("ALR-SITE002-1792667216"))
			.andExpect(jsonPath("$.content[0].siteName").value("Usine Lyon Vénissieux"))
			.andExpect(jsonPath("$.content[0].timestamp").value("2026-10-22T10:38:56Z"))
			.andExpect(jsonPath("$.content[0].recent").value(true))
			.andExpect(jsonPath("$.page.totalElements").value(1))
			.andExpect(jsonPath("$.page.size").value(50));
	}

	@Test
	@WithMockUser(username = USER_ID)
	void shouldBindLowercaseFilters_whenFiltersAreGiven() throws Exception {
		// given
		AlertSearchRequest request = new AlertSearchRequest(
				"SITE002",
				Set.of(AlertSeverity.HIGH, AlertSeverity.CRITICAL),
				Set.of(AlertType.SPIKE),
				Instant.parse("2026-10-22T08:00:00Z"),
				Instant.parse("2026-10-22T12:00:00Z"));
		when(alertService.getAlerts(USER, request, 1, 20)).thenReturn(Page.empty(PageRequest.of(1, 20)));

		// when / then
		mockMvc.perform(get("/api/v1/alerts")
				.param("siteId", "SITE002")
				.param("severity", "high,critical")
				.param("type", "spike")
				.param("from", "2026-10-22T08:00:00Z")
				.param("to", "2026-10-22T12:00:00Z")
				.param("page", "1")
				.param("size", "20"))
			.andExpect(status().isOk())
			.andExpect(jsonPath("$.content").isEmpty());
	}

	@Test
	@WithMockUser(username = USER_ID)
	void shouldReturn400_whenSeverityIsUnknown() throws Exception {
		mockMvc.perform(get("/api/v1/alerts").param("severity", "urgent"))
			.andExpect(status().isBadRequest());
		verifyNoInteractions(alertService);
	}

	@Test
	@WithMockUser(username = USER_ID)
	void shouldReturn400_whenPageSizeIsTooLarge() throws Exception {
		mockMvc.perform(get("/api/v1/alerts").param("size", "201"))
			.andExpect(status().isBadRequest());
		verifyNoInteractions(alertService);
	}

	@Test
	@WithMockUser(username = USER_ID)
	void shouldReturn400ProblemDetail_whenPeriodIsInvalid() throws Exception {
		// given
		Instant from = Instant.parse("2026-10-22T12:00:00Z");
		Instant to = Instant.parse("2026-10-22T08:00:00Z");
		when(alertService.getAlerts(eq(USER), any(), anyInt(), anyInt()))
			.thenThrow(new InvalidAlertPeriodException(from, to));

		// when / then
		mockMvc.perform(get("/api/v1/alerts").param("from", from.toString()).param("to", to.toString()))
			.andExpect(status().isBadRequest())
			.andExpect(jsonPath("$.detail").value(
					"Invalid period: from (2026-10-22T12:00:00Z) is after to (2026-10-22T08:00:00Z)"));
	}

	@Test
	@WithMockUser(username = USER_ID)
	void shouldReturn404ProblemDetail_whenSiteIsNotVisible() throws Exception {
		// given
		when(alertService.getAlerts(eq(USER), any(), anyInt(), anyInt()))
			.thenThrow(new AlertSiteNotFoundException("SITE999"));

		// when / then
		mockMvc.perform(get("/api/v1/alerts").param("siteId", "SITE999"))
			.andExpect(status().isNotFound())
			.andExpect(jsonPath("$.detail").value("Site SITE999 not found"));
	}

	@Test
	@WithMockUser(username = USER_ID)
	void shouldReturnSummary_whenSiteIsGiven() throws Exception {
		// given
		when(alertService.getSummary(USER, "SITE002")).thenReturn(new AlertSummaryResponse(
				Instant.parse("2026-10-22T10:07:00Z"), 3,
				Map.of("low", 0L, "medium", 1L, "high", 2L, "critical", 0L)));

		// when / then
		mockMvc.perform(get("/api/v1/alerts/summary").param("siteId", "SITE002"))
			.andExpect(status().isOk())
			.andExpect(jsonPath("$.total").value(3))
			.andExpect(jsonPath("$.bySeverity.high").value(2));
	}

	private static AlertResponse alert() {
		return new AlertResponse(
				"ALR-SITE002-1792667216",
				"SITE002",
				"Usine Lyon Vénissieux",
				Instant.parse("2026-10-22T10:38:56Z"),
				"high",
				"spike",
				"Pic de consommation détecté sur Usine Lyon Vénissieux",
				912.5,
				720.0,
				true);
	}

}
