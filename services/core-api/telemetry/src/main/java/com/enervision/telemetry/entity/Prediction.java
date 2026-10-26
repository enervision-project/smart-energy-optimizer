package com.enervision.telemetry.entity;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Table;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;
import org.hibernate.annotations.Immutable;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;

/** Hourly energy forecast written by the prediction jobs, never updated by core-api. */
@Entity
@Immutable
@Table(name = "predictions")
@Getter
@Setter
@NoArgsConstructor
public class Prediction {

	@Id
	@Column(name = "prediction_id")
	private UUID predictionId;

	@ManyToOne(fetch = FetchType.LAZY, optional = false)
	@JoinColumn(name = "run_id", nullable = false)
	private PredictionRun run;

	@Column(name = "site_id", nullable = false)
	private String siteId;

	@Column(name = "predicted_for", nullable = false)
	private Instant predictedFor;

	@Column(name = "prediction_kwh", nullable = false, precision = 14, scale = 3)
	private BigDecimal predictionKwh;

}
