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
@Order(2)
public class VoltageRecommendationRule implements RecommendationRule {

	private static final double NOMINAL_VOLTAGE = 400.0;

	private static final String GOOD_SHORT = "Tension stable et optimale. Vos équipements fonctionnent en toute sécurité.";
	private static final String GOOD_LONG = "La tension de votre réseau est parfaitement stable et reste très proche de sa valeur nominale. "
			+ "Vos appareils électriques opèrent dans leurs conditions de conception idéales, ce qui préserve au maximum leur durée de vie, évite les surchauffes inutiles et garantit une efficacité énergétique maximale.";

	private static final String MEDIUM_SHORT = "Fluctuations de tension détectées. Surveillez l'état de vos équipements électroniques sensibles.";
	private static final String MEDIUM_LONG = "Votre tension présente des variations notables tout en restant à la limite des tolérances acceptables. "
			+ "Bien qu'il n'y ait pas de danger immédiat pour la plupart des machines, ces fluctuations régulières peuvent fatiguer prématurément les composants de vos appareils les plus sensibles. "
			+ "Il est conseillé de surveiller la fréquence de ces écarts.";

	private static final String BAD_SHORT = "Tension critique hors tolérance. Risque élevé de dommages matériels, une intervention est requise.";
	private static final String BAD_LONG = "Les écarts de tension dépassent les seuils de sécurité, ce qui expose directement vos équipements à des risques de pannes, de réinitialisations intempestives ou de dommages irréversibles liés aux sous-tensions ou surtensions. "
			+ "Il est urgent de contacter votre gestionnaire de réseau électrique pour vérifier la distribution, ou d'envisager l'installation d'un régulateur/onduleur pour protéger vos installations.";

	@Override
	public RecommendationType type() {
		return RecommendationType.VOLTAGE;
	}

	@Override
	public RecommendationItemResponse evaluate(SiteResponse site, HourlyReading reading) {
		BigDecimal rawVoltage = reading.getVoltageV();
		if (rawVoltage == null) {
			return RecommendationItemResponse.missing(type());
		}

		double voltage = rawVoltage.doubleValue();
		double roundedValue = RecommendationRule.round(voltage, 1);
		double deviationPercent = Math.abs(voltage - NOMINAL_VOLTAGE) / NOMINAL_VOLTAGE * 100.0;

		if (deviationPercent <= 5.0) {
			return RecommendationItemResponse.of(
					type(), roundedValue, RecommendationQuality.GOOD, GOOD_SHORT, GOOD_LONG);
		}
		if (deviationPercent <= 10.0) {
			return RecommendationItemResponse.of(
					type(), roundedValue, RecommendationQuality.MEDIUM, MEDIUM_SHORT, MEDIUM_LONG);
		}
		return RecommendationItemResponse.of(
				type(), roundedValue, RecommendationQuality.BAD, BAD_SHORT, BAD_LONG);
	}

}
