package com.enervision.configuration.api.controller;

import com.enervision.common.security.CurrentUser;
import com.enervision.common.security.CurrentUserWebConfig;
import com.enervision.common.security.Role;
import com.enervision.configuration.api.dto.SiteResponse;
import com.enervision.configuration.api.dto.SiteSummaryResponse;
import com.enervision.configuration.exception.SiteNotFoundException;
import com.enervision.configuration.service.SiteService;
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

@WebMvcTest(SiteController.class)
@Import(CurrentUserWebConfig.class)
class SiteControllerTest {

	/** Authentication name = JWT subject = user id. */
	private static final String USER_ID = "3f2c8a1e-7b4d-4c1a-9e2f-5a6b7c8d9e0f";

	@Autowired
	private MockMvc mockMvc;

	@MockitoBean
	private SiteService siteService;

	@Test
	void shouldReturn401_whenNotAuthenticated() throws Exception {
		mockMvc.perform(get("/api/v1/sites"))
			.andExpect(status().isUnauthorized());
	}

	@Test
	@WithMockUser(username = USER_ID, roles = "ADMIN")
	void shouldListSitesInCamelCase_whenUserIsAdmin() throws Exception {
		// given
		when(siteService.getSites(new CurrentUser(UUID.fromString(USER_ID), Role.ADMIN))).thenReturn(List.of(
				new SiteSummaryResponse("SITE001", "Bureau Paris", "office", "Paris, France", 200, "active")));

		// when / then
		mockMvc.perform(get("/api/v1/sites"))
			.andExpect(status().isOk())
			.andExpect(jsonPath("$[0].siteId").value("SITE001"))
			.andExpect(jsonPath("$[0].capacityKw").value(200.0));
	}

	@Test
	@WithMockUser(username = USER_ID)
	void shouldPassCurrentUser_whenUserRole() throws Exception {
		// given
		when(siteService.getSite(new CurrentUser(UUID.fromString(USER_ID), Role.USER), "SITE001")).thenReturn(
				new SiteResponse("SITE001", "Bureau Paris", "office", "Paris, France", 200, "active", Instant.EPOCH,
						null));

		// when / then
		mockMvc.perform(get("/api/v1/sites/SITE001"))
			.andExpect(status().isOk())
			.andExpect(jsonPath("$.siteId").value("SITE001"))
			.andExpect(jsonPath("$.profile").isEmpty());
	}

	@Test
	@WithMockUser(username = USER_ID)
	void shouldReturn404ProblemDetail_whenSiteNotFound() throws Exception {
		// given
		when(siteService.getSite(new CurrentUser(UUID.fromString(USER_ID), Role.USER), "SITE999"))
			.thenThrow(new SiteNotFoundException("SITE999"));

		// when / then
		mockMvc.perform(get("/api/v1/sites/SITE999"))
			.andExpect(status().isNotFound())
			.andExpect(jsonPath("$.detail").value("Site SITE999 not found"));
	}

}
