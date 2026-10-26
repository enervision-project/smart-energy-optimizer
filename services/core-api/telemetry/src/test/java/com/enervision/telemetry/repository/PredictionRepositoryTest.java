package com.enervision.telemetry.repository;

import com.enervision.telemetry.entity.Prediction;
import jakarta.persistence.EntityManager;
import org.hibernate.Hibernate;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.data.jpa.test.autoconfigure.DataJpaTest;
import org.springframework.boot.jdbc.test.autoconfigure.AutoConfigureTestDatabase;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.postgresql.PostgreSQLContainer;
import org.testcontainers.utility.DockerImageName;

import javax.sql.DataSource;
import java.math.BigDecimal;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.List;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;

/** Queries and Hibernate mappings are checked against the forecast schema on TimescaleDB. */
@DataJpaTest(properties = "spring.jpa.hibernate.ddl-auto=validate")
@Testcontainers
@AutoConfigureTestDatabase(replace = AutoConfigureTestDatabase.Replace.NONE)
class PredictionRepositoryTest {

	@Container
	@ServiceConnection
	static final PostgreSQLContainer POSTGRES = new PostgreSQLContainer(
			DockerImageName.parse("timescale/timescaledb:2.17.2-pg16").asCompatibleSubstituteFor("postgres"))
		.withInitScript("predictions-schema.sql");

	private static final Instant T0 = Instant.parse("2026-10-26T10:00:00Z");
	private static final UUID LOW = UUID.fromString("00000000-0000-0000-0000-000000000001");
	private static final UUID HIGH = UUID.fromString("00000000-0000-0000-0000-000000000002");
	private static final UUID OTHER = UUID.fromString("00000000-0000-0000-0000-000000000003");

	@Autowired
	private PredictionRepository predictionRepository;

	@Autowired
	private DataSource dataSource;

	@Autowired
	private EntityManager entityManager;

	private JdbcClient jdbcClient;

	@BeforeEach
	void setUp() {
		jdbcClient = JdbcClient.create(dataSource);
	}

	@Test
	void shouldSelectTheLatestRunPerSiteAndHour_preservingOlderHoursAndExclusiveBounds() {
		// given: UUID order differs from publication order; another site's newer run must not hide this site.
		insertRun(HIGH, T0.minus(Duration.ofHours(2)), "old");
		insertRun(LOW, T0.minus(Duration.ofHours(1)), "new");
		insertRun(OTHER, T0.minus(Duration.ofMinutes(30)), "other-site");
		insert(HIGH, "SITE001", T0.minusSeconds(3600), "900");
		insert(HIGH, "SITE001", T0, "100");
		insert(HIGH, "SITE001", T0.plusSeconds(3600), "101");
		insert(LOW, "SITE001", T0.plusSeconds(3600), "123.456");
		insert(LOW, "SITE001", T0.plusSeconds(7200), "0.000");
		insert(LOW, "SITE001", T0.plusSeconds(10800), "999");
		insert(OTHER, "SITE002", T0, "777");

		// when
		List<Prediction> predictions = predictionRepository.findLatestForSite("SITE001", T0,
				T0.plus(Duration.ofHours(3)));

		// then
		assertThat(predictions).extracting(Prediction::getPredictedFor)
			.containsExactly(T0, T0.plusSeconds(3600), T0.plusSeconds(7200));
		assertThat(predictions).extracting(prediction -> prediction.getRun().getRunId())
			.containsExactly(HIGH, LOW, LOW);
		assertThat(predictions.get(1).getPredictionKwh()).isEqualByComparingTo("123.456");
		assertThat(predictions.getLast().getPredictionKwh()).isEqualByComparingTo("0");
		assertThat(Hibernate.isInitialized(predictions.get(1).getRun())).isTrue();
		assertThat(predictions.get(1).getRun().getModelVersion()).isEqualTo("new");
		assertThat(predictions.get(1).getRun().getGeneratedAt()).isEqualTo(T0.minus(Duration.ofHours(1)));
	}

	@Test
	void shouldBreakEqualGenerationTimeTiesByRunId() {
		// given
		insertRun(HIGH, T0.minusSeconds(3600), "high");
		insertRun(LOW, T0.minusSeconds(3600), "low");
		insert(HIGH, "SITE001", T0, "222.222");
		insert(LOW, "SITE001", T0, "111.111");

		// when / then
		assertThat(predictionRepository.findLatestForSite("SITE001", T0, T0.plusSeconds(3600)))
			.singleElement().satisfies(prediction -> {
				assertThat(prediction.getRun().getRunId()).isEqualTo(HIGH);
				assertThat(prediction.getPredictionKwh()).isEqualByComparingTo("222.222");
			});
	}

	@Test
	void shouldReturnNoRows_whenTheSiteHasNoForecast() {
		assertThat(predictionRepository.findLatestForSite("SITE001", T0, T0.plusSeconds(3600))).isEmpty();
	}

	@Test
	void shouldNeverFlushChangesToExternallyOwnedForecastsOrRuns() {
		// given
		insertRun(LOW, T0.minusSeconds(3600), "original");
		insert(LOW, "SITE001", T0, "123.456");
		Prediction prediction = predictionRepository.findLatestForSite("SITE001", T0, T0.plusSeconds(3600))
			.getFirst();

		// when
		prediction.setPredictionKwh(new BigDecimal("999.999"));
		prediction.getRun().setModelVersion("changed");
		entityManager.flush();

		// then: both mappings are immutable, even if setters are called accidentally.
		assertThat(jdbcClient.sql("SELECT prediction_kwh FROM predictions WHERE run_id = :run")
			.param("run", LOW).query(BigDecimal.class).single()).isEqualByComparingTo("123.456");
		assertThat(jdbcClient.sql("SELECT model_version FROM prediction_runs WHERE run_id = :run")
			.param("run", LOW).query(String.class).single()).isEqualTo("original");
	}

	private void insertRun(UUID runId, Instant generatedAt, String version) {
		jdbcClient.sql("""
				INSERT INTO prediction_runs
				    (run_id, model_name, model_version, window_start, window_end, generated_at,
				     site_count, prediction_count, status)
				VALUES (:id, 'hourly-consumption', :version, :start, :end, :generated, 2, 48, 'complete')
				""")
			.param("id", runId)
			.param("version", version)
			.param("start", T0.minus(Duration.ofDays(1)).atOffset(ZoneOffset.UTC))
			.param("end", T0.plus(Duration.ofDays(1)).atOffset(ZoneOffset.UTC))
			.param("generated", generatedAt.atOffset(ZoneOffset.UTC))
			.update();
	}

	private void insert(UUID runId, String siteId, Instant ts, String value) {
		jdbcClient.sql("""
				INSERT INTO predictions (run_id, site_id, predicted_for, prediction_kwh)
				VALUES (:run, :site, :ts, :value)
				""")
			.param("run", runId)
			.param("site", siteId)
			.param("ts", ts.atOffset(ZoneOffset.UTC))
			.param("value", new BigDecimal(value))
			.update();
	}

}
