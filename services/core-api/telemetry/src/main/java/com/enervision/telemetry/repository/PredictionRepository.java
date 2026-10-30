package com.enervision.telemetry.repository;

import com.enervision.telemetry.entity.Prediction;
import org.springframework.data.jpa.repository.EntityGraph;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.Repository;
import org.springframework.data.repository.query.Param;

import java.time.Instant;
import java.util.List;
import java.util.UUID;

/** Read-only repository: one latest complete publication per site and target hour. */
public interface PredictionRepository extends Repository<Prediction, UUID> {

	/** Keeps the latest complete run for each hour; run ids break generation-time ties. */
	@EntityGraph(attributePaths = "run")
	@Query("""
			SELECT prediction FROM Prediction prediction
			WHERE prediction.siteId = :siteId
			    AND prediction.predictedFor >= :from
			    AND prediction.predictedFor < :to
			    AND prediction.run.status = 'complete'
			    AND NOT EXISTS (
			        SELECT newer.predictionId FROM Prediction newer
			        WHERE newer.siteId = prediction.siteId
			            AND newer.predictedFor = prediction.predictedFor
			            AND newer.run.status = 'complete'
			            AND (newer.run.generatedAt > prediction.run.generatedAt
			                OR (newer.run.generatedAt = prediction.run.generatedAt
			                    AND newer.run.runId > prediction.run.runId))
			    )
			ORDER BY prediction.predictedFor
			""")
	List<Prediction> findLatestForSite(@Param("siteId") String siteId, @Param("from") Instant from,
			@Param("to") Instant to);

}
