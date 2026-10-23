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
@Order(3)
public class LoadRateRecommendationRule implements RecommendationRule {

	private static final double NOMINAL_VOLTAGE = 400.0;
	private static final double NOMINAL_COS_PHI = 0.93;
	private static final double SQRT_THREE = Math.sqrt(3.0);

	private static final String GOOD_SHORT = "Votre taux de charge est optimal. Votre réseau électrique fonctionne en toute sécurité avec une marge confortable.";
	private static final String GOOD_LONG = "L'intensité appelée par vos équipements est bien en deçà de la limite de votre installation. "
			+ "Vos câbles et disjoncteurs ne subissent aucun stress thermique, ce qui écarte tout risque de coupure par surcharge. "
			+ "Vous disposez d'une réserve de puissance suffisante pour ajouter de nouveaux appareils sans modifier votre infrastructure.";

	private static final String MEDIUM_SHORT = "Taux de charge élevé. Soyez vigilant quant à l'utilisation simultanée de vos gros équipements pour éviter une coupure.";
	private static final String MEDIUM_LONG = "Votre installation s'approche de sa capacité maximale. Si le fonctionnement reste sécurisé, l'activation simultanée de plusieurs appareils énergivores (ou le pic de démarrage de certains moteurs) risque de faire sauter vos disjoncteurs. "
			+ "Il est recommandé de lisser votre consommation en décalant l'utilisation de certaines machines ou de planifier un audit si vous prévoyez d'ajouter de nouveaux équipements.";

	private static final String BAD_SHORT = "Surcharge imminente. Réduisez immédiatement la charge pour éviter un déclenchement ou une surchauffe dangereuse des câbles.";
	private static final String BAD_LONG = "Votre circuit électrique est saturé et fonctionne dangereusement près de sa limite de rupture. "
			+ "Cette situation expose votre installation à des coupures de courant intempestives et à un vieillissement accéléré (voire une surchauffe) du câblage, augmentant les risques d'incendie. "
			+ "Il faut impérativement réduire la charge en éteignant les équipements non essentiels et envisager rapidement un rééquilibrage de vos phases ou une augmentation de la puissance de votre abonnement.";

	@Override
	public RecommendationType type() {
		return RecommendationType.LOAD_RATE;
	}

	@Override
	public RecommendationItemResponse evaluate(SiteResponse site, HourlyReading reading) {
		BigDecimal rawCurrent = reading.getCurrentA();
		double capacityKw = site.capacityKw();
		if (rawCurrent == null || capacityKw <= 0) {
			return RecommendationItemResponse.missing(type());
		}

		double nominalCurrent = (capacityKw * 1000.0) / (SQRT_THREE * NOMINAL_VOLTAGE * NOMINAL_COS_PHI);
		double loadRate = (rawCurrent.doubleValue() / nominalCurrent) * 100.0;
		double roundedValue = RecommendationRule.round(loadRate, 1);

		if (roundedValue <= 80.0) {
			return RecommendationItemResponse.of(
					type(), roundedValue, RecommendationQuality.GOOD, GOOD_SHORT, GOOD_LONG);
		}
		if (roundedValue <= 95.0) {
			return RecommendationItemResponse.of(
					type(), roundedValue, RecommendationQuality.MEDIUM, MEDIUM_SHORT, MEDIUM_LONG);
		}
		return RecommendationItemResponse.of(
				type(), roundedValue, RecommendationQuality.BAD, BAD_SHORT, BAD_LONG);
	}

}
