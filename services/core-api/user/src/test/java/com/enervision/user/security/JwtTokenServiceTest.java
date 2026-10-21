package com.enervision.user.security;

import com.enervision.user.api.dto.TokenResponse;
import com.enervision.user.entities.Role;
import com.enervision.user.entities.User;
import org.junit.jupiter.api.Test;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtException;

import javax.crypto.SecretKey;
import java.time.Duration;
import java.util.Base64;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class JwtTokenServiceTest {

	private static final String SECRET = Base64.getEncoder().encodeToString(new byte[32]);
	private static final JwtProperties PROPERTIES = new JwtProperties(SECRET, Duration.ofHours(1), "enervision-test");

	private final JwtConfig jwtConfig = new JwtConfig();
	private final SecretKey secretKey = jwtConfig.jwtSecretKey(PROPERTIES);
	private final JwtTokenService tokenService = new JwtTokenService(jwtConfig.jwtEncoder(secretKey), PROPERTIES);
	private final JwtDecoder jwtDecoder = jwtConfig.jwtDecoder(secretKey, PROPERTIES);

	@Test
	void shouldGenerateDecodableToken_whenUserIsValid() {
		// given
		User user = user(Role.ADMIN);

		// when
		TokenResponse response = tokenService.generateToken(user);

		// then
		Jwt jwt = jwtDecoder.decode(response.accessToken());
		assertThat(jwt.getSubject()).isEqualTo(user.getId().toString());
		assertThat(jwt.getClaimAsString("email")).isEqualTo("jane@example.com");
		assertThat(jwt.getClaimAsStringList(JwtTokenService.ROLES_CLAIM)).containsExactly("ADMIN");
		assertThat(response.tokenType()).isEqualTo("Bearer");
		assertThat(response.expiresIn()).isEqualTo(3600);
	}

	@Test
	void shouldMapRolesClaimToAuthorities_whenTokenIsDecoded() {
		// given
		Jwt jwt = jwtDecoder.decode(tokenService.generateToken(user(Role.USER)).accessToken());

		// when
		var authentication = jwtConfig.jwtAuthenticationConverter().convert(jwt);

		// then (Spring Security 7 also adds the FACTOR_BEARER factor authority)
		assertThat(authentication.getAuthorities())
			.extracting(GrantedAuthority::getAuthority)
			.contains("ROLE_USER")
			.doesNotContain("ROLE_ADMIN");
	}

	@Test
	void shouldRejectToken_whenIssuerDiffers() {
		// given
		JwtProperties otherIssuer = new JwtProperties(SECRET, Duration.ofHours(1), "autre-emetteur");
		String token = new JwtTokenService(jwtConfig.jwtEncoder(secretKey), otherIssuer)
			.generateToken(user(Role.USER))
			.accessToken();

		// when / then
		assertThatThrownBy(() -> jwtDecoder.decode(token)).isInstanceOf(JwtException.class);
	}

	@Test
	void shouldFailAtStartup_whenSecretIsTooShort() {
		// given
		JwtProperties shortSecret = new JwtProperties(
				Base64.getEncoder().encodeToString(new byte[16]), Duration.ofHours(1), "enervision-test");

		// when / then
		assertThatThrownBy(() -> jwtConfig.jwtSecretKey(shortSecret)).isInstanceOf(IllegalStateException.class);
	}

	private static User user(Role role) {
		User user = new User();
		user.setId(UUID.randomUUID());
		user.setEmail("jane@example.com");
		user.setRole(role);
		return user;
	}

}
