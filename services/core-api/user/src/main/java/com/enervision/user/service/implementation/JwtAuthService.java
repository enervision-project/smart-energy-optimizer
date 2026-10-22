package com.enervision.user.service.implementation;

import com.enervision.user.api.dto.LoginRequest;
import com.enervision.user.api.dto.TokenResponse;
import com.enervision.user.entity.User;
import com.enervision.user.repository.UserRepository;
import com.enervision.user.security.TokenService;
import com.enervision.user.service.AuthService;
import lombok.RequiredArgsConstructor;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.Locale;

@Service
@RequiredArgsConstructor
@Transactional(readOnly = true)
class JwtAuthService implements AuthService {

	private final UserRepository userRepository;
	private final AuthenticationManager authenticationManager;
	private final TokenService tokenService;

	@Override
	public TokenResponse login(LoginRequest request) {
		String email = normalizeEmail(request.email());
		// throws BadCredentialsException if the email or password is wrong
		authenticationManager
			.authenticate(UsernamePasswordAuthenticationToken.unauthenticated(email, request.password()));
		User user = userRepository.findByEmail(email)
			.orElseThrow(() -> new BadCredentialsException("Invalid credentials"));
		return tokenService.generateToken(user);
	}

	private static String normalizeEmail(String email) {
		return email.trim().toLowerCase(Locale.ROOT);
	}

}
