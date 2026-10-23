package com.enervision.diagnostic.repository;

import com.enervision.diagnostic.entity.HourlyReading;
import com.enervision.diagnostic.entity.HourlyReadingId;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.Optional;

public interface HourlyReadingRepository extends JpaRepository<HourlyReading, HourlyReadingId> {

	Optional<HourlyReading> findFirstBySiteIdOrderByTsDesc(String siteId);

}
