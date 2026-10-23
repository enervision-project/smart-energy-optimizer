package com.enervision.diagnostic.entity;

/**
 * Types of energy recommendations computed by the diagnostic module.
 */
public enum RecommendationType {

	POWER_FACTOR("POWER_FACTOR", "Facteur de puissance", ""),
	VOLTAGE("VOLTAGE", "Voltage", "V"),
	LOAD_RATE("LOAD_RATE", "Taux de charge", "%");

	private final String code;
	private final String label;
	private final String unit;

	RecommendationType(String code, String label, String unit) {
		this.code = code;
		this.label = label;
		this.unit = unit;
	}

	public String code() {
		return code;
	}

	public String label() {
		return label;
	}

	public String unit() {
		return unit;
	}

}
