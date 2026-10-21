package com.enervision.configuration.repository;

import com.enervision.configuration.entity.UserSite;
import com.enervision.configuration.entity.UserSiteId;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

@Repository
public interface UserSiteRepository extends JpaRepository<UserSite, UserSiteId> {
}
