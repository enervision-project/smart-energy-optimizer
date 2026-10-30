package com.enervision.diagnostic.entity;

public enum RecommendationQuality {

	GOOD("good"),
	MEDIUM("medium"),
	BAD("bad"),
	UNKNOWN("unknown");

	private final String code;

	RecommendationQuality(String code) {
		this.code = code;
	}

	public String code() {
		return code;
	}

}
