package com.enervision.configuration.service.implementation;

import com.enervision.common.security.CurrentUser;
import com.enervision.configuration.api.dto.SiteResponse;
import com.enervision.configuration.api.dto.SiteSummaryResponse;
import com.enervision.configuration.entity.Site;
import com.enervision.configuration.entity.UserSiteId;
import com.enervision.configuration.exception.SiteNotFoundException;
import com.enervision.configuration.mapper.SiteMapper;
import com.enervision.configuration.repository.SiteProfileRepository;
import com.enervision.configuration.repository.SiteRepository;
import com.enervision.configuration.repository.UserSiteRepository;
import com.enervision.configuration.service.SiteService;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;

@Service
@RequiredArgsConstructor
@Transactional(readOnly = true)
class DefaultSiteService implements SiteService {

	private final SiteRepository siteRepository;
	private final SiteProfileRepository siteProfileRepository;
	private final UserSiteRepository userSiteRepository;
	private final SiteMapper siteMapper;

	@Override
	public List<SiteSummaryResponse> getSites(CurrentUser user) {
		List<Site> sites = user.isAdmin()
			? siteRepository.findAllByOrderBySiteIdAsc()
			: siteRepository.findAllVisibleBy(user.id());
		return sites.stream()
			.map(siteMapper::toSummaryResponse)
			.toList();
	}

	@Override
	public SiteResponse getSite(CurrentUser user, String siteId) {
		if (!canView(user, siteId)) {
			throw new SiteNotFoundException(siteId);
		}
		Site site = siteRepository.findById(siteId)
			.orElseThrow(() -> new SiteNotFoundException(siteId));
		return siteMapper.toResponse(site, siteProfileRepository.findById(siteId).orElse(null));
	}

	@Override
	public boolean canView(CurrentUser user, String siteId) {
		return user.isAdmin() || userSiteRepository.existsById(new UserSiteId(user.id(), siteId));
	}

}
