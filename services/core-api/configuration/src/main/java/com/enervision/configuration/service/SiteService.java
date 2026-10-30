package com.enervision.configuration.service;

import com.enervision.common.security.CurrentUser;
import com.enervision.configuration.api.dto.SiteResponse;
import com.enervision.configuration.api.dto.SiteSummaryResponse;

import java.util.List;

/** An admin sees every site, any other user only those granted in {@code users_sites}. */
public interface SiteService {

	List<SiteSummaryResponse> getSites(CurrentUser user);

	/** Site with its reference profile; a site the user cannot see is reported as not found. */
	SiteResponse getSite(CurrentUser user, String siteId);

	boolean canView(CurrentUser user, String siteId);

}
