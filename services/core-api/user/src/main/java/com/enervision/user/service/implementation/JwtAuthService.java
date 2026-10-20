package com.enervision.user.service.implementation;

import com.enervision.user.api.dto.LoginRequest;
import com.enervision.user.api.dto.RegisterRequest;
import com.enervision.user.api.dto.TokenResponse;
import com.enervision.user.api.dto.UserResponse;
import com.enervision.user.domain.Role;
import com.enervision.user.domain.User;
import com.enervision.user.exception.EmailAlreadyUsedException;
import com.enervision.user.mapper.UserMapper;
import com.enervision.user.repository.UserRepository;
import com.enervision.user.security.TokenService;
import com.enervision.user.service.AuthService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.Locale;

@Slf4j
@Service
@RequiredArgsConstructor
@Transactional(readOnly = true)
class JwtAuthService implements AuthService {

	private final UserRepository userRepository;
	private final UserMapper userMapper;
	private final PasswordEncoder passwordEncoder;
	private final AuthenticationManager authenticationManager;
	private final TokenService tokenService;

	@Override
	@Transactional
	public UserResponse register(RegisterRequest request) {
		String email = normalizeEmail(request.email());
		if (userRepository.existsByEmail(email)) {
			throw new EmailAlreadyUsedException(email);
		}
		User user = userMapper.toEntity(request);
		user.setEmail(email);
		user.setPassword(passwordEncoder.encode(request.password()));
		user.setRole(Role.USER);
		// flush so that createdAt/updatedAt are populated in the response
		User savedUser = userRepository.saveAndFlush(user);
		log.info("User {} registered", savedUser.getId());
		return userMapper.toResponse(savedUser);
	}

	@Override
	public TokenResponse login(LoginRequest request) {
		String email = normalizeEmail(request.email());
		// throws BadCredentialsException if the email or password is wrong
		authenticationManager.authenticate(UsernamePasswordAuthenticationToken.unauthenticated(email, request.password()));
		User user = userRepository.findByEmail(email)
			.orElseThrow(() -> new BadCredentialsException("Invalid credentials"));
		return tokenService.generateToken(user);
	}

	private static String normalizeEmail(String email) {
		return email.trim().toLowerCase(Locale.ROOT);
	}

}
