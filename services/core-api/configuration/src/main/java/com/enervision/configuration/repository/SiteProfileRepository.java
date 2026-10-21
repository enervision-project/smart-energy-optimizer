package com.enervision.configuration.repository;

import com.enervision.configuration.entity.SiteProfile;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

@Repository
public interface SiteProfileRepository extends JpaRepository<SiteProfile, String> {
}
