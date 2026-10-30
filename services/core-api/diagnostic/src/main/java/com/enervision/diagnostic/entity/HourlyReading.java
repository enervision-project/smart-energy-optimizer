package com.enervision.diagnostic.entity;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.IdClass;
import jakarta.persistence.Table;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;
import org.hibernate.annotations.Immutable;

import java.math.BigDecimal;
import java.time.Instant;

/** Read-only: rows are written by the ETL worker. */
@Entity
@Immutable
@Table(name = "readings_hours")
@IdClass(HourlyReadingId.class)
@Getter
@Setter
@NoArgsConstructor
public class HourlyReading {

	@Id
	@Column(name = "site_id")
	private String siteId;

	@Id
	@Column(name = "ts")
	private Instant ts;

	@Column(name = "consumption_kwh", precision = 14, scale = 2)
	private BigDecimal consumptionKwh;

	@Column(name = "voltage_v", precision = 14, scale = 2)
	private BigDecimal voltageV;

	@Column(name = "current_a", precision = 14, scale = 2)
	private BigDecimal currentA;

	@Column(name = "power_factor", precision = 14, scale = 2)
	private BigDecimal powerFactor;

	@Column(name = "temperature_celsius", precision = 14, scale = 2)
	private BigDecimal temperatureCelsius;

	@Column(name = "humidity_percent", precision = 14, scale = 2)
	private BigDecimal humidityPercent;

}
