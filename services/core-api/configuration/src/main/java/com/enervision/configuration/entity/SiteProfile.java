package com.enervision.configuration.entity;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;
import org.hibernate.annotations.Immutable;

import java.math.BigDecimal;

/**
 * Reference profile of a site (expected normal behaviour), at most one per site.
 * Read-only: rows are loaded by a dedicated script.
 */
@Entity
@Immutable
@Table(name = "site_profiles")
@Getter
@Setter
@NoArgsConstructor
public class SiteProfile {

	@Id
	@Column(name = "site_id")
	private String siteId;

	/** Expected consumption at rest (kW). */
	@Column(name = "base_consumption", nullable = false, precision = 14, scale = 2)
	private BigDecimal baseConsumption;

	/** Expected consumption peak during activity (kW). */
	@Column(name = "peak_consumption", nullable = false, precision = 14, scale = 2)
	private BigDecimal peakConsumption;

	/** Start of the activity range, in hours (inclusive). */
	@Column(name = "working_hour_start", nullable = false)
	private short workingHourStart;

	/** End of the activity range, in hours (exclusive): 0 to 24 for a site active around the clock. */
	@Column(name = "working_hour_end", nullable = false)
	private short workingHourEnd;

	/** Activity days, ISO numbering: 1 = Monday … 7 = Sunday. */
	@Column(name = "working_days", nullable = false)
	private Short[] workingDays;

	@Column(name = "seasonal_variation", precision = 5, scale = 4)
	private BigDecimal seasonalVariation;

	@Column(name = "noise_level", precision = 5, scale = 4)
	private BigDecimal noiseLevel;

	/** Weekend consumption multiplier, e.g. 1.2 for +20 %; {@code null} when the site has none. */
	@Column(name = "weekend_factor", precision = 5, scale = 4)
	private BigDecimal weekendFactor;

	@Column(name = "shift_pattern", nullable = false)
	private boolean shiftPattern;

}
