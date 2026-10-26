package com.enervision.diagnostic.api.dto;

import com.enervision.diagnostic.entity.RecommendationQuality;
import com.enervision.diagnostic.entity.RecommendationType;
import org.jspecify.annotations.Nullable;

public record RecommendationItemResponse(
		String type,
		String label,
		@Nullable Double value,
		String unit,
		String quality,
		String shortRecommendation,
		String longRecommendation) {

	public static final String MISSING_SHORT = "Données de mesure indisponibles pour ce paramètre.";
	public static final String MISSING_LONG = "Les capteurs n'ont pas transmis de données valides pour cette grandeur. "
			+ "Vérifiez la connectivité et l'état de l'équipement de mesure.";

	public static RecommendationItemResponse of(
			RecommendationType type,
			@Nullable Double value,
			RecommendationQuality quality,
			String shortRecommendation,
			String longRecommendation) {
		return new RecommendationItemResponse(
				type.code(),
				type.label(),
				value,
				type.unit(),
				quality.code(),
				shortRecommendation,
				longRecommendation);
	}

	public static RecommendationItemResponse missing(RecommendationType type) {
		return of(type, null, RecommendationQuality.UNKNOWN, MISSING_SHORT, MISSING_LONG);
	}

}
