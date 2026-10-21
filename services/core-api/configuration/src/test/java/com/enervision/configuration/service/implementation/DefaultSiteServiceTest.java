package com.enervision.configuration.service.implementation;

import com.enervision.common.security.CurrentUser;
import com.enervision.common.security.Role;
import com.enervision.configuration.api.dto.SiteResponse;
import com.enervision.configuration.api.dto.SiteSummaryResponse;
import com.enervision.configuration.api.dto.WorkingHoursResponse;
import com.enervision.configuration.entity.Site;
import com.enervision.configuration.entity.SiteProfile;
import com.enervision.configuration.entity.UserSiteId;
import com.enervision.configuration.exception.SiteNotFoundException;
import com.enervision.configuration.mapper.SiteMapper;
import com.enervision.configuration.repository.SiteProfileRepository;
import com.enervision.configuration.repository.SiteRepository;
import com.enervision.configuration.repository.UserSiteRepository;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.Spy;
import org.mockito.junit.jupiter.MockitoExtension;

import java.math.BigDecimal;
import java.time.DayOfWeek;
import java.util.List;
import java.util.Optional;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class DefaultSiteServiceTest {

	private static final UUID USER_ID = UUID.randomUUID();
	private static final CurrentUser ADMIN = new CurrentUser(USER_ID, Role.ADMIN);
	private static final CurrentUser USER = new CurrentUser(USER_ID, Role.USER);

	@Mock
	private SiteRepository siteRepository;

	@Mock
	private SiteProfileRepository siteProfileRepository;

	@Mock
	private UserSiteRepository userSiteRepository;

	@Spy
	private SiteMapper siteMapper = new SiteMapper();

	@InjectMocks
	private DefaultSiteService siteService;

	@Test
	void shouldReturnAllSites_whenUserIsAdmin() {
		// given
		when(siteRepository.findAllByOrderBySiteIdAsc()).thenReturn(List.of(site("SITE001"), site("SITE002")));

		// when
		List<SiteSummaryResponse> sites = siteService.getSites(ADMIN);

		// then
		assertThat(sites).extracting(SiteSummaryResponse::siteId).containsExactly("SITE001", "SITE002");
		verify(siteRepository, never()).findAllVisibleBy(any());
	}

	@Test
	void shouldReturnGrantedSitesOnly_whenUserIsNotAdmin() {
		// given
		when(siteRepository.findAllVisibleBy(USER_ID)).thenReturn(List.of(site("SITE001")));

		// when
		List<SiteSummaryResponse> sites = siteService.getSites(USER);

		// then
		assertThat(sites).extracting(SiteSummaryResponse::siteId).containsExactly("SITE001");
		verify(siteRepository, never()).findAllByOrderBySiteIdAsc();
	}

	@Test
	void shouldReturnSiteWithProfile_whenProfileExists() {
		// given
		SiteProfile profile = new SiteProfile();
		profile.setSiteId("SITE001");
		profile.setBaseConsumption(new BigDecimal("20.00"));
		profile.setPeakConsumption(new BigDecimal("150.00"));
		profile.setWorkingHourStart((short) 8);
		profile.setWorkingHourEnd((short) 19);
		profile.setWorkingDays(new Short[] {5, 1, 2, 3, 4});
		profile.setWeekendFactor(new BigDecimal("1.2000"));
		when(siteRepository.findById("SITE001")).thenReturn(Optional.of(site("SITE001")));
		when(siteProfileRepository.findById("SITE001")).thenReturn(Optional.of(profile));

		// when
		SiteResponse response = siteService.getSite(ADMIN, "SITE001");

		// then
		assertThat(response.profile()).isNotNull();
		assertThat(response.profile().workingHours()).isEqualTo(new WorkingHoursResponse(8, 19));
		assertThat(response.profile().workingDays()).containsExactly(
				DayOfWeek.MONDAY, DayOfWeek.TUESDAY, DayOfWeek.WEDNESDAY, DayOfWeek.THURSDAY, DayOfWeek.FRIDAY);
		assertThat(response.profile().weekendFactor()).isEqualByComparingTo("1.2");
	}

	@Test
	void shouldReturnSiteWithoutProfile_whenNoProfileIsLoaded() {
		// given
		when(siteRepository.findById("SITE001")).thenReturn(Optional.of(site("SITE001")));
		when(siteProfileRepository.findById("SITE001")).thenReturn(Optional.empty());

		// when
		SiteResponse response = siteService.getSite(ADMIN, "SITE001");

		// then
		assertThat(response.siteId()).isEqualTo("SITE001");
		assertThat(response.profile()).isNull();
	}

	@Test
	void shouldReturnSite_whenUserHasBeenGrantedTheSite() {
		// given
		when(userSiteRepository.existsById(new UserSiteId(USER_ID, "SITE001"))).thenReturn(true);
		when(siteRepository.findById("SITE001")).thenReturn(Optional.of(site("SITE001")));

		// when
		SiteResponse response = siteService.getSite(USER, "SITE001");

		// then
		assertThat(response.siteId()).isEqualTo("SITE001");
	}

	@Test
	void shouldThrowSiteNotFound_whenUserHasNotBeenGrantedTheSite() {
		// given
		when(userSiteRepository.existsById(new UserSiteId(USER_ID, "SITE002"))).thenReturn(false);

		// when / then
		assertThatThrownBy(() -> siteService.getSite(USER, "SITE002")).isInstanceOf(SiteNotFoundException.class);
		verify(siteRepository, never()).findById(any());
	}

	@Test
	void shouldThrowSiteNotFound_whenSiteDoesNotExist() {
		// given
		when(siteRepository.findById("SITE999")).thenReturn(Optional.empty());

		// when / then
		assertThatThrownBy(() -> siteService.getSite(ADMIN, "SITE999")).isInstanceOf(SiteNotFoundException.class);
	}

	@Test
	void shouldAllowAdminToViewAnySite_withoutCheckingGrants() {
		// when
		boolean canView = siteService.canView(ADMIN, "SITE001");

		// then
		assertThat(canView).isTrue();
		verify(userSiteRepository, never()).existsById(any());
	}

	private static Site site(String siteId) {
		Site site = new Site();
		site.setSiteId(siteId);
		site.setSiteName("Site " + siteId);
		site.setSiteType("office");
		site.setCapacityKw(200);
		site.setStatus("active");
		return site;
	}

}
