package com.enervision.diagnostic.service.rule;

import com.enervision.configuration.api.dto.SiteResponse;
import com.enervision.diagnostic.api.dto.RecommendationItemResponse;
import com.enervision.diagnostic.entity.HourlyReading;
import com.enervision.diagnostic.entity.RecommendationQuality;
import com.enervision.diagnostic.entity.RecommendationType;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

import java.math.BigDecimal;

@Component
@Order(1)
public class PowerFactorRecommendationRule implements RecommendationRule {

	private static final String GOOD_SHORT = "Votre facteur de puissance est excellent. Aucune action n'est requise, votre installation est énergétiquement optimisée.";
	private static final String GOOD_LONG = "Votre installation présente un excellent facteur de puissance, indiquant une utilisation très efficace de l'énergie électrique. "
			+ "Vous tirez le meilleur parti de vos équipements tout en évitant les pénalités tarifaires de votre fournisseur. "
			+ "Maintenez simplement vos routines de maintenance préventive pour conserver ce niveau de performance sur le long terme.";

	private static final String MEDIUM_SHORT = "Votre facteur de puissance est acceptable mais perfectible. Surveillez vos équipements pour éviter de glisser vers la zone de pénalité.";
	private static final String MEDIUM_LONG = "Votre facteur de puissance est correct, mais la marge de sécurité avant d'atteindre les seuils de pénalité financière est faible. "
			+ "Il est conseillé d'identifier les charges inductives (moteurs, transformateurs) qui consomment de l'énergie réactive. "
			+ "Optimiser leur utilisation, notamment en évitant de faire tourner des machines à vide ou sous-chargées, vous permettra de repasser dans la zone optimale à moindre coût.";

	private static final String BAD_SHORT = "Votre facteur de puissance est trop faible et génère des surcoûts. Une intervention technique est nécessaire pour compenser l'énergie réactive.";
	private static final String BAD_LONG = "Votre installation consomme une part trop importante d'énergie réactive, ce qui surcharge votre réseau interne, diminue la durée de vie de vos équipements et déclenche des pénalités sur votre facture d'électricité. "
			+ "Il est vivement recommandé de faire réaliser un audit par un électricien professionnel. "
			+ "L'installation de batteries de condensateurs sera très probablement nécessaire, un investissement généralement vite amorti par les économies directes sur vos factures.";

	@Override
	public RecommendationType type() {
		return RecommendationType.POWER_FACTOR;
	}

	@Override
	public RecommendationItemResponse evaluate(SiteResponse site, HourlyReading reading) {
		BigDecimal rawPowerFactor = reading.getPowerFactor();
		if (rawPowerFactor == null) {
			return RecommendationItemResponse.missing(type());
		}

		double roundedValue = RecommendationRule.round(rawPowerFactor.doubleValue(), 2);
		if (roundedValue >= 0.95) {
			return RecommendationItemResponse.of(
					type(), roundedValue, RecommendationQuality.GOOD, GOOD_SHORT, GOOD_LONG);
		}
		if (roundedValue >= 0.93) {
			return RecommendationItemResponse.of(
					type(), roundedValue, RecommendationQuality.MEDIUM, MEDIUM_SHORT, MEDIUM_LONG);
		}
		return RecommendationItemResponse.of(
				type(), roundedValue, RecommendationQuality.BAD, BAD_SHORT, BAD_LONG);
	}

}
