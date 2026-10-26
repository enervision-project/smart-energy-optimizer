package com.enervision.telemetry.repository;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.jdbc.test.autoconfigure.AutoConfigureTestDatabase;
import org.springframework.boot.jdbc.test.autoconfigure.JdbcTest;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.context.annotation.Import;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.test.context.jdbc.Sql;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.postgresql.PostgreSQLContainer;

import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * Native SQL on a real PostgreSQL ({@code date_bin}, arrays, {@code DISTINCT ON}). Each test runs in a transaction
 * rolled back at the end, schema included ({@code @Sql}).
 */
@JdbcTest
@Testcontainers
@AutoConfigureTestDatabase(replace = AutoConfigureTestDatabase.Replace.NONE)
@Import(ReadingRepository.class)
@Sql("/readings-schema.sql")
class ReadingRepositoryTest {

	@Container
	@ServiceConnection
	static final PostgreSQLContainer POSTGRES = new PostgreSQLContainer("postgres:16-alpine");

	private static final Instant T0 = Instant.parse("2026-10-26T10:00:00Z");

	@Autowired
	private ReadingRepository readingRepository;

	@Autowired
	private JdbcClient jdbcClient;

	@Test
	void shouldAggregateEachStep_withWorstQualityImputationAndNullReasons() {
		// given: four minutes in the 10:00 quarter, one in the 10:15 quarter, one outside the period
		insert("SITE001", 0, 100.0, null, null, "good", "current");
		insert("SITE001", 1, null, 110.0, "linear", "degraded", "current", "consumption_sensor_failure");
		insert("SITE001", 2, 120.0, null, null, "partial", "backfill", "temperature_sensor_failure");
		insert("SITE001", 3, 130.0, null, null, "partial", "current", "temperature_sensor_failure",
				"humidity_sensor_failure");
		insert("SITE001", 16, 200.0, null, null, "good", "current");
		insert("SITE001", 30, 999.0, null, null, "critical", "current");
		insert("SITE003", 0, 700.0, null, null, "good", "current");

		// when
		List<BucketRow> buckets = readingRepository.findBuckets("SITE001", Duration.ofMinutes(15), T0,
				T0.plus(Duration.ofMinutes(30)));

		// then
		assertThat(buckets).extracting(BucketRow::bucket)
			.containsExactly(T0, T0.plus(Duration.ofMinutes(15)));
		BucketRow first = buckets.getFirst();
		assertThat(first.consumptionKw()).isEqualTo(116.67);
		assertThat(first.consumptionKwImputed()).isEqualTo(115.0);
		assertThat(first.powerFactor()).isEqualTo(0.915);
		assertThat(first.worstQuality()).isEqualTo(2);
		assertThat(first.minutesReceived()).isEqualTo(4);
		assertThat(first.minutesWithConsumption()).isEqualTo(3);
		assertThat(first.minutesBackfilled()).isEqualTo(1);
		assertThat(first.minutesImputed()).isEqualTo(1);
		assertThat(first.imputationMethods()).containsExactly("linear");
		assertThat(first.nullReasons()).containsExactly("consumption_sensor_failure", "humidity_sensor_failure",
				"temperature_sensor_failure");
		assertThat(buckets.getLast().nullReasons()).isEmpty();
		assertThat(buckets.getLast().imputationMethods()).isEmpty();
	}

	@Test
	void shouldReturnTheLastReadingOfASite() {
		// given
		insert("SITE001", 0, 100.0, null, null, "good", "current");
		insert("SITE001", 5, null, 101.0, "previous_value", "degraded", "backfill", "consumption_sensor_failure");

		// when / then
		assertThat(readingRepository.findLatest("SITE001")).hasValueSatisfying(row -> {
			assertThat(row.ts()).isEqualTo(T0.plus(Duration.ofMinutes(5)));
			assertThat(row.source()).isEqualTo("backfill");
			assertThat(row.consumptionKw()).isNull();
			assertThat(row.consumptionKwImputed()).isEqualTo(101.0);
			assertThat(row.imputationMethod()).isEqualTo("previous_value");
			assertThat(row.nullReasons()).containsExactly("consumption_sensor_failure");
			assertThat(row.dataQuality()).isEqualTo("degraded");
		});
		assertThat(readingRepository.findLatest("SITE003")).isEmpty();
	}

	@Test
	void shouldReturnOneRecentReadingPerSite() {
		// given
		insert("SITE001", 0, 100.0, null, null, "good", "current");
		insert("SITE001", 9, 105.0, null, null, "good", "current");
		insert("SITE003", 2, 700.0, null, null, "good", "current");

		// when
		List<ReadingRow> rows = readingRepository.findLatestPerSite(List.of("SITE001", "SITE003"),
				T0.plus(Duration.ofMinutes(5)));

		// then: SITE003's only reading is older than "since"
		assertThat(rows).singleElement().satisfies(row -> {
			assertThat(row.siteId()).isEqualTo("SITE001");
			assertThat(row.consumptionKw()).isEqualTo(105.0);
		});
	}

	@Test
	void shouldSummarizeRawValues_withEnergyAsSumOfHourlyAverages() {
		// given: 10:00 hour averages 150 kW, 11:00 hour 300 kW
		insert("SITE001", 0, 100.0, null, null, "good", "current");
		insert("SITE001", 30, 200.0, null, null, "good", "current");
		insert("SITE001", 45, null, 190.0, "linear", "degraded", "current", "consumption_sensor_failure");
		insert("SITE001", 70, 300.0, null, null, "good", "current");

		// when
		SummaryRow summary = readingRepository.summarize("SITE001", T0, T0.plus(Duration.ofHours(2)));

		// then
		assertThat(summary.energyKwh()).isEqualTo(450.0);
		assertThat(summary.hoursWithData()).isEqualTo(2);
		assertThat(summary.peakKw()).isEqualTo(300.0);
		assertThat(summary.peakAt()).isEqualTo(T0.plus(Duration.ofMinutes(70)));
		assertThat(summary.minutesReceived()).isEqualTo(4);
		assertThat(summary.minutesWithConsumption()).isEqualTo(3);
		assertThat(summary.minutesImputed()).isEqualTo(1);
	}

	@Test
	void shouldSummarizeAnEmptyPeriod_withNullsAndZeros() {
		// when
		SummaryRow summary = readingRepository.summarize("SITE001", T0, T0.plus(Duration.ofHours(1)));

		// then
		assertThat(summary.energyKwh()).isNull();
		assertThat(summary.peakKw()).isNull();
		assertThat(summary.peakAt()).isNull();
		assertThat(summary.hoursWithData()).isZero();
		assertThat(summary.minutesReceived()).isZero();
	}

	private void insert(String siteId, int minute, Double consumptionKw, Double imputedKw, String method,
			String quality, String source, String... nullReasons) {
		jdbcClient.sql("""
				INSERT INTO readings_raws (site_id, ts, consumption_kw, voltage_v, current_a, power_factor,
				    temperature_celsius, humidity_percent, null_reasons, data_quality, source,
				    consumption_kw_imputed, imputation_method)
				VALUES (:siteId, :ts, :kw, 230, 10, 0.915, 21, 40, CAST(:reasons AS text[]), :quality, :source,
				    :imputed, :method)""")
			.param("siteId", siteId)
			.param("ts", T0.plus(Duration.ofMinutes(minute)).atOffset(ZoneOffset.UTC))
			.param("kw", consumptionKw)
			.param("reasons", "{" + String.join(",", nullReasons) + "}")
			.param("quality", quality)
			.param("source", source)
			.param("imputed", imputedKw)
			.param("method", method)
			.update();
	}

}
