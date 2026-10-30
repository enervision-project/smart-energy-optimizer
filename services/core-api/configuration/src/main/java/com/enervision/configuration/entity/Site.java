package com.enervision.configuration.entity;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;
import org.hibernate.annotations.Immutable;

import java.time.Instant;

/** Monitored site. Read-only: rows are written by the ETL worker from the energy API. */
@Entity
@Immutable
@Table(name = "sites")
@Getter
@Setter
@NoArgsConstructor
public class Site {

	@Id
	@Column(name = "site_id")
	private String siteId;

	@Column(name = "site_name", nullable = false)
	private String siteName;

	@Column(name = "site_type", nullable = false)
	private String siteType;

	@Column(name = "location")
	private String location;

	@Column(name = "capacity_kw", nullable = false)
	private double capacityKw;

	@Column(name = "status", nullable = false)
	private String status;

	@Column(name = "updated_at", nullable = false)
	private Instant updatedAt;

}
