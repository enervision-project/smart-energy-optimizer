package com.enervision.diagnostic.repository;

import com.enervision.diagnostic.entity.Alert;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.JpaSpecificationExecutor;
import org.springframework.data.jpa.repository.Query;
import org.springframework.stereotype.Repository;

import java.time.Instant;
import java.util.Collection;
import java.util.List;

@Repository
public interface AlertRepository extends JpaRepository<Alert, String>, JpaSpecificationExecutor<Alert> {

	@Query("""
			select new com.enervision.diagnostic.repository.SeverityCount(a.severity, count(a))
			from Alert a
			where a.siteId in :siteIds and a.timestamp >= :since
			group by a.severity""")
	List<SeverityCount> countBySeveritySince(Collection<String> siteIds, Instant since);

}
