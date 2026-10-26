package com.enervision.telemetry.repository;

import lombok.RequiredArgsConstructor;
import org.jspecify.annotations.Nullable;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;

import java.sql.Array;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.Duration;
import java.time.Instant;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.Arrays;
import java.util.Collection;
import java.util.List;
import java.util.Optional;

/**
 * Read-only queries on {@code readings_raws}, written by the ETL worker (one row per site and per minute).
 * Native SQL: aggregates per step ({@code date_bin}) and PostgreSQL arrays are out of JPQL's reach.
 * Steps are aligned on UTC ({@code date_bin} origin 2000-01-01T00:00Z).
 */
@Repository
@RequiredArgsConstructor
public class ReadingRepository {

	private static final String READING_COLUMNS = """
			r.site_id, r.ts, r.source, r.consumption_kw, r.consumption_kw_imputed, r.imputation_method,
			r.voltage_v, r.current_a, r.power_factor, r.temperature_celsius, r.humidity_percent,
			r.null_reasons, r.data_quality""";

	private static final String BUCKETS = """
			SELECT date_bin(CAST(:step AS interval), r.ts, TIMESTAMPTZ '2000-01-01 00:00:00+00') AS bucket,
			       round(avg(r.consumption_kw)::numeric, 2) AS consumption_kw,
			       round(avg(coalesce(r.consumption_kw, r.consumption_kw_imputed))::numeric, 2)
			           AS consumption_kw_imputed,
			       round(avg(r.voltage_v)::numeric, 2) AS voltage_v,
			       round(avg(r.current_a)::numeric, 2) AS current_a,
			       round(avg(r.power_factor)::numeric, 3) AS power_factor,
			       round(avg(r.temperature_celsius)::numeric, 2) AS temperature_celsius,
			       round(avg(r.humidity_percent)::numeric, 2) AS humidity_percent,
			       max(CASE r.data_quality WHEN 'good' THEN 0 WHEN 'partial' THEN 1
			                               WHEN 'degraded' THEN 2 ELSE 3 END) AS worst_quality,
			       count(*) AS minutes_received,
			       count(*) FILTER (WHERE r.source = 'backfill') AS minutes_backfilled,
			       count(r.consumption_kw_imputed) AS minutes_imputed,
			       string_agg(DISTINCT r.imputation_method, ',') AS imputation_methods,
			       string_agg(DISTINCT nullif(array_to_string(r.null_reasons, ','), ''), ',') AS null_reasons
			FROM readings_raws AS r
			WHERE r.site_id = :siteId AND r.ts >= :from AND r.ts < :to
			GROUP BY bucket
			ORDER BY bucket""";

	private static final String LATEST = "SELECT " + READING_COLUMNS + """

			FROM readings_raws AS r
			WHERE r.site_id = :siteId
			ORDER BY r.ts DESC
			LIMIT 1""";

	private static final String LATEST_PER_SITE = "SELECT DISTINCT ON (r.site_id) " + READING_COLUMNS + """

			FROM readings_raws AS r
			WHERE r.site_id IN (:siteIds) AND r.ts >= :since
			ORDER BY r.site_id, r.ts DESC""";

	/** Energy = sum of the hourly averages of the raw power (an average kW over an hour is that hour's kWh). */
	private static final String SUMMARY = """
			WITH period AS (
			    SELECT r.ts, r.consumption_kw, r.consumption_kw_imputed
			    FROM readings_raws AS r
			    WHERE r.site_id = :siteId AND r.ts >= :from AND r.ts < :to
			),
			hours AS (
			    SELECT avg(p.consumption_kw) AS kw
			    FROM period AS p
			    GROUP BY date_bin(INTERVAL '1 hour', p.ts, TIMESTAMPTZ '2000-01-01 00:00:00+00')
			),
			peak AS (
			    SELECT p.ts, p.consumption_kw
			    FROM period AS p
			    WHERE p.consumption_kw IS NOT NULL
			    ORDER BY p.consumption_kw DESC, p.ts
			    LIMIT 1
			)
			SELECT (SELECT round(sum(h.kw)::numeric, 2) FROM hours AS h) AS energy_kwh,
			       (SELECT count(h.kw) FROM hours AS h) AS hours_with_data,
			       (SELECT pk.consumption_kw FROM peak AS pk) AS peak_kw,
			       (SELECT pk.ts FROM peak AS pk) AS peak_at,
			       (SELECT count(*) FROM period) AS minutes_received,
			       (SELECT count(p.consumption_kw) FROM period AS p) AS minutes_with_consumption,
			       (SELECT count(p.consumption_kw_imputed) FROM period AS p) AS minutes_imputed""";

	private final JdbcClient jdbcClient;

	/** Steps of {@code [from, to)} holding at least one reading, oldest first. */
	public List<BucketRow> findBuckets(String siteId, Duration step, Instant from, Instant to) {
		return jdbcClient.sql(BUCKETS)
			.param("step", step.toMinutes() + " minutes")
			.param("siteId", siteId)
			.param("from", utc(from))
			.param("to", utc(to))
			.query((rs, rowNum) -> new BucketRow(
					instant(rs, "bucket"),
					nullableDouble(rs, "consumption_kw"),
					nullableDouble(rs, "consumption_kw_imputed"),
					nullableDouble(rs, "voltage_v"),
					nullableDouble(rs, "current_a"),
					nullableDouble(rs, "power_factor"),
					nullableDouble(rs, "temperature_celsius"),
					nullableDouble(rs, "humidity_percent"),
					rs.getInt("worst_quality"),
					rs.getInt("minutes_received"),
					rs.getInt("minutes_backfilled"),
					rs.getInt("minutes_imputed"),
					distinctValues(rs.getString("imputation_methods")),
					distinctValues(rs.getString("null_reasons"))))
			.list();
	}

	public Optional<ReadingRow> findLatest(String siteId) {
		return jdbcClient.sql(LATEST)
			.param("siteId", siteId)
			.query(ReadingRepository::readingRow)
			.optional();
	}

	/** Last reading of each site taken since {@code since}; a site without one is absent from the result. */
	public List<ReadingRow> findLatestPerSite(Collection<String> siteIds, Instant since) {
		return jdbcClient.sql(LATEST_PER_SITE)
			.param("siteIds", siteIds)
			.param("since", utc(since))
			.query(ReadingRepository::readingRow)
			.list();
	}

	public SummaryRow summarize(String siteId, Instant from, Instant to) {
		return jdbcClient.sql(SUMMARY)
			.param("siteId", siteId)
			.param("from", utc(from))
			.param("to", utc(to))
			.query((rs, rowNum) -> new SummaryRow(
					nullableDouble(rs, "energy_kwh"),
					rs.getInt("hours_with_data"),
					nullableDouble(rs, "peak_kw"),
					nullableInstant(rs, "peak_at"),
					rs.getInt("minutes_received"),
					rs.getInt("minutes_with_consumption"),
					rs.getInt("minutes_imputed")))
			.single();
	}

	private static ReadingRow readingRow(ResultSet rs, int rowNum) throws SQLException {
		return new ReadingRow(
				rs.getString("site_id"),
				instant(rs, "ts"),
				rs.getString("source"),
				nullableDouble(rs, "consumption_kw"),
				nullableDouble(rs, "consumption_kw_imputed"),
				rs.getString("imputation_method"),
				nullableDouble(rs, "voltage_v"),
				nullableDouble(rs, "current_a"),
				nullableDouble(rs, "power_factor"),
				nullableDouble(rs, "temperature_celsius"),
				nullableDouble(rs, "humidity_percent"),
				textArray(rs.getArray("null_reasons")),
				rs.getString("data_quality"));
	}

	/** The PostgreSQL driver maps {@code timestamptz} to {@link OffsetDateTime}, not to {@link Instant}. */
	private static OffsetDateTime utc(Instant instant) {
		return instant.atOffset(ZoneOffset.UTC);
	}

	private static Instant instant(ResultSet rs, String column) throws SQLException {
		return rs.getObject(column, OffsetDateTime.class).toInstant();
	}

	private static @Nullable Instant nullableInstant(ResultSet rs, String column) throws SQLException {
		OffsetDateTime value = rs.getObject(column, OffsetDateTime.class);
		return value == null ? null : value.toInstant();
	}

	private static @Nullable Double nullableDouble(ResultSet rs, String column) throws SQLException {
		Object value = rs.getObject(column);
		return value == null ? null : ((Number) value).doubleValue();
	}

	private static List<String> textArray(@Nullable Array array) throws SQLException {
		return array == null ? List.of() : List.of((String[]) array.getArray());
	}

	/** Comma-separated values aggregated by {@code string_agg}, deduplicated and sorted. */
	private static List<String> distinctValues(@Nullable String joined) {
		if (joined == null || joined.isEmpty()) {
			return List.of();
		}
		return Arrays.stream(joined.split(",")).distinct().sorted().toList();
	}

}
