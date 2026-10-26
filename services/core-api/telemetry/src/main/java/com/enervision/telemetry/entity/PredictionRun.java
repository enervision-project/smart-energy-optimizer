package com.enervision.telemetry.entity;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;
import org.hibernate.annotations.Immutable;

import java.time.Instant;
import java.util.UUID;

/** Publication metadata written by the prediction jobs; core-api only reads it. */
@Entity
@Immutable
@Table(name = "prediction_runs")
@Getter
@Setter
@NoArgsConstructor
public class PredictionRun {

	@Id
	@Column(name = "run_id")
	private UUID runId;

	@Column(name = "model_name", nullable = false)
	private String modelName;

	@Column(name = "model_version", nullable = false)
	private String modelVersion;

	@Column(name = "generated_at", nullable = false)
	private Instant generatedAt;

	@Column(name = "status", nullable = false)
	private String status;

}
