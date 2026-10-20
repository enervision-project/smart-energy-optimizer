package com.enervision.user.security;

import com.enervision.user.api.dto.TokenResponse;
import com.enervision.user.domain.User;
import lombok.RequiredArgsConstructor;
import org.springframework.security.oauth2.jose.jws.MacAlgorithm;
import org.springframework.security.oauth2.jwt.JwsHeader;
import org.springframework.security.oauth2.jwt.JwtClaimsSet;
import org.springframework.security.oauth2.jwt.JwtEncoder;
import org.springframework.security.oauth2.jwt.JwtEncoderParameters;
import org.springframework.stereotype.Service;

import java.time.Instant;
import java.util.List;

/**
 * HS256-signed JWTs. The subject is the user id; roles are in the {@value #ROLES_CLAIM} claim.
 */
@Service
@RequiredArgsConstructor
class JwtTokenService implements TokenService {

	static final String ROLES_CLAIM = "roles";
	static final String EMAIL_CLAIM = "email";

	private static final String TOKEN_TYPE = "Bearer";

	private final JwtEncoder jwtEncoder;
	private final JwtProperties jwtProperties;

	@Override
	public TokenResponse generateToken(User user) {
		Instant now = Instant.now();
		JwtClaimsSet claims = JwtClaimsSet.builder()
			.issuer(jwtProperties.issuer())
			.subject(user.getId().toString())
			.issuedAt(now)
			.expiresAt(now.plus(jwtProperties.expiration()))
			.claim(EMAIL_CLAIM, user.getEmail())
			.claim(ROLES_CLAIM, List.of(user.getRole().name()))
			.build();
		JwsHeader header = JwsHeader.with(MacAlgorithm.HS256).build();
		String token = jwtEncoder.encode(JwtEncoderParameters.from(header, claims)).getTokenValue();
		return new TokenResponse(token, TOKEN_TYPE, jwtProperties.expiration().toSeconds());
	}

}
