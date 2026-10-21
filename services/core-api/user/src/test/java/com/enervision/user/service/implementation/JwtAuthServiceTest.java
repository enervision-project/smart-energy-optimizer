package com.enervision.user.service.implementation;

import com.enervision.user.api.dto.LoginRequest;
import com.enervision.user.api.dto.TokenResponse;
import com.enervision.user.entity.User;
import com.enervision.user.repository.UserRepository;
import com.enervision.user.security.TokenService;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;

import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class JwtAuthServiceTest {

	@Mock
	private UserRepository userRepository;

	@Mock
	private AuthenticationManager authenticationManager;

	@Mock
	private TokenService tokenService;

	@InjectMocks
	private JwtAuthService authService;

	@Test
	void shouldReturnToken_whenCredentialsAreValid() {
		// given
		User user = new User();
		user.setEmail("jane@example.com");
		TokenResponse token = new TokenResponse("jwt", "Bearer", 3600);
		when(userRepository.findByEmail("jane@example.com")).thenReturn(Optional.of(user));
		when(tokenService.generateToken(user)).thenReturn(token);

		// when
		TokenResponse response = authService.login(new LoginRequest("Jane@Example.com", "password123"));

		// then
		assertThat(response).isEqualTo(token);
		verify(authenticationManager)
			.authenticate(UsernamePasswordAuthenticationToken.unauthenticated("jane@example.com", "password123"));
	}

	@Test
	void shouldPropagateBadCredentials_whenPasswordIsWrong() {
		// given
		when(authenticationManager.authenticate(any())).thenThrow(new BadCredentialsException("bad"));

		// when / then
		assertThatThrownBy(() -> authService.login(new LoginRequest("jane@example.com", "wrong")))
			.isInstanceOf(BadCredentialsException.class);
		verify(tokenService, never()).generateToken(any());
	}

}
