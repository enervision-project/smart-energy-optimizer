package com.enervision.diagnostic.repository;

import com.enervision.diagnostic.entity.Alert;
import jakarta.persistence.criteria.Predicate;
import org.springframework.data.jpa.domain.Specification;

import java.time.Instant;
import java.util.ArrayList;
import java.util.Collection;
import java.util.List;

public final class AlertSpecifications {

	private AlertSpecifications() {
	}

	/** An empty severity or type collection means no filter on that field. */
	public static Specification<Alert> matching(Collection<String> siteIds, Collection<String> severities,
			Collection<String> types, Instant from, Instant to) {
		return (root, query, builder) -> {
			List<Predicate> predicates = new ArrayList<>();
			predicates.add(root.get("siteId").in(siteIds));
			if (!severities.isEmpty()) {
				predicates.add(root.get("severity").in(severities));
			}
			if (!types.isEmpty()) {
				predicates.add(root.get("type").in(types));
			}
			predicates.add(builder.greaterThanOrEqualTo(root.get("timestamp"), from));
			predicates.add(builder.lessThanOrEqualTo(root.get("timestamp"), to));
			return builder.and(predicates.toArray(Predicate[]::new));
		};
	}

}
