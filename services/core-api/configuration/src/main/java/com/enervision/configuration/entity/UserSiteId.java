package com.enervision.configuration.entity;

import jakarta.persistence.Column;
import jakarta.persistence.Embeddable;

import java.io.Serializable;
import java.util.UUID;

@Embeddable
public record UserSiteId(
		@Column(name = "user_id") UUID userId,
		@Column(name = "site_id") String siteId) implements Serializable {
}
