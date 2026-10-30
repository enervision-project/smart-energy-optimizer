package com.enervision.diagnostic.entity;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;
import org.hibernate.annotations.Immutable;

import java.time.Instant;

/** Read-only, written by the ETL; raw strings so that an unexpected value cannot break reads. */
@Entity
@Immutable
@Table(name = "alerts")
@Getter
@Setter
@NoArgsConstructor
public class Alert {

	@Id
	@Column(name = "alert_id")
	private String alertId;

	/** Quoted: {@code timestamp} is a reserved word in SQL. */
	@Column(name = "\"timestamp\"", nullable = false)
	private Instant timestamp;

	@Column(name = "site_id", nullable = false)
	private String siteId;

	@Column(name = "severity", nullable = false)
	private String severity;

	@Column(name = "type", nullable = false)
	private String type;

	@Column(name = "message", nullable = false)
	private String message;

	@Column(name = "value")
	private Double value;

	@Column(name = "threshold", nullable = false)
	private double threshold;

	@Column(name = "loaded_at", nullable = false)
	private Instant loadedAt;

}
