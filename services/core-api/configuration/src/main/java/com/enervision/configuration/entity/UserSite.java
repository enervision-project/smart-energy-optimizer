package com.enervision.configuration.entity;

import jakarta.persistence.EmbeddedId;
import jakarta.persistence.Entity;
import jakarta.persistence.Table;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;
import org.hibernate.annotations.Immutable;

/** Holds the user id only, without a JPA link to the user module's entity; an ADMIN has no row. */
@Entity
@Immutable
@Table(name = "users_sites")
@Getter
@Setter
@NoArgsConstructor
public class UserSite {

	@EmbeddedId
	private UserSiteId id;

}
