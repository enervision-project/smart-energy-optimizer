package com.enervision.configuration.repository;

import com.enervision.configuration.entity.Site;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.stereotype.Repository;

import java.util.List;
import java.util.UUID;

@Repository
public interface SiteRepository extends JpaRepository<Site, String> {

	List<Site> findAllByOrderBySiteIdAsc();

	@Query("""
			select s from Site s
			where exists (select 1 from UserSite us where us.id.siteId = s.siteId and us.id.userId = :userId)
			order by s.siteId""")
	List<Site> findAllVisibleBy(UUID userId);

}
