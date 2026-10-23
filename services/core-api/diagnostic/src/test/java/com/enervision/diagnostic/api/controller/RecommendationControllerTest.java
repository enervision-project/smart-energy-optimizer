package com.enervision.diagnostic.api.controller;

import com.enervision.common.security.CurrentUser;
import com.enervision.common.security.CurrentUserWebConfig;
import com.enervision.common.security.Role;
import com.enervision.configuration.exception.SiteNotFoundException;
import com.enervision.diagnostic.api.dto.RecommendationItemResponse;
import com.enervision.diagnostic.api.dto.RecommendationResponse;
import com.enervision.diagnostic.service.RecommendationService;
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

import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(RecommendationController.class)
@Import(CurrentUserWebConfig.class)
class RecommendationControllerTest {

	private static final String USER_ID = "3f2c8a1e-7b4d-4c1a-9e2f-5a6b7c8d9e0f";
	private static final CurrentUser USER = new CurrentUser(UUID.fromString(USER_ID), Role.USER);
	private static final String SITE_ID = "SITE001";

	@Autowired
	private MockMvc mockMvc;

	@MockitoBean
	private RecommendationService recommendationService;

	@Test
	void shouldReturn401_whenNotAuthenticated() throws Exception {
		mockMvc.perform(get("/api/v1/recommendations/" + SITE_ID))
			.andExpect(status().isUnauthorized());
	}

	@Test
	@WithMockUser(username = USER_ID)
	void shouldReturn200WithRecommendationsInCamelCase_whenReadingExists() throws Exception {
		RecommendationResponse response = new RecommendationResponse(
				SITE_ID,
				Instant.parse("2026-10-23T10:00:00Z"),
				List.of(new RecommendationItemResponse(
						"POWER_FACTOR",
						"Facteur de puissance",
						0.98,
						"",
						"good",
						"Votre facteur de puissance est excellent.",
						"Votre installation présente un excellent facteur de puissance...")));
		when(recommendationService.getRecommendation(USER, SITE_ID)).thenReturn(Optional.of(response));

		mockMvc.perform(get("/api/v1/recommendations/" + SITE_ID))
			.andExpect(status().isOk())
			.andExpect(jsonPath("$.siteId").value(SITE_ID))
			.andExpect(jsonPath("$.timestamp").value("2026-10-23T10:00:00Z"))
			.andExpect(jsonPath("$.items[0].type").value("POWER_FACTOR"))
			.andExpect(jsonPath("$.items[0].label").value("Facteur de puissance"))
			.andExpect(jsonPath("$.items[0].value").value(0.98))
			.andExpect(jsonPath("$.items[0].unit").value(""))
			.andExpect(jsonPath("$.items[0].quality").value("good"))
			.andExpect(jsonPath("$.items[0].shortRecommendation").value("Votre facteur de puissance est excellent."))
			.andExpect(jsonPath("$.items[0].longRecommendation")
				.value("Votre installation présente un excellent facteur de puissance..."));
	}

	@Test
	@WithMockUser(username = USER_ID)
	void shouldReturn204NoContent_whenNoReadingsExist() throws Exception {
		when(recommendationService.getRecommendation(USER, SITE_ID)).thenReturn(Optional.empty());

		mockMvc.perform(get("/api/v1/recommendations/" + SITE_ID))
			.andExpect(status().isNoContent());
	}

	@Test
	@WithMockUser(username = USER_ID)
	void shouldReturn404ProblemDetail_whenSiteNotFound() throws Exception {
		when(recommendationService.getRecommendation(USER, SITE_ID))
			.thenThrow(new SiteNotFoundException(SITE_ID));

		mockMvc.perform(get("/api/v1/recommendations/" + SITE_ID))
			.andExpect(status().isNotFound())
			.andExpect(jsonPath("$.detail").value("Site SITE001 not found"));
	}

}
