package com.enervision.user.security;

import com.enervision.common.security.Role;
import com.enervision.user.entity.User;
import com.enervision.user.repository.UserRepository;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.security.crypto.password.PasswordEncoder;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class InitialAdminInitializerTest {

	private static final String PASSWORD = "a-long-password";

	@Mock
	private UserRepository userRepository;

	@Mock
	private PasswordEncoder passwordEncoder;

	private InitialAdminInitializer initializer(String email, String password) {
		return new InitialAdminInitializer(new InitialAdminProperties(email, password), userRepository,
				passwordEncoder);
	}

	@Test
	void shouldCreateAdmin_whenNoUserExists() {
		// given
		when(userRepository.count()).thenReturn(0L);
		when(passwordEncoder.encode(PASSWORD)).thenReturn("{bcrypt}hash");

		// when
		initializer(" Admin@Example.com ", PASSWORD).run(null);

		// then
		ArgumentCaptor<User> saved = ArgumentCaptor.forClass(User.class);
		verify(userRepository).save(saved.capture());
		assertThat(saved.getValue().getEmail()).isEqualTo("admin@example.com");
		assertThat(saved.getValue().getPassword()).isEqualTo("{bcrypt}hash");
		assertThat(saved.getValue().getRole()).isEqualTo(Role.ADMIN);
	}

	@Test
	void shouldDoNothing_whenUsersAlreadyExist() {
		// given
		when(userRepository.count()).thenReturn(3L);

		// when
		initializer("admin@example.com", PASSWORD).run(null);

		// then
		verify(userRepository, never()).save(any());
	}

	@Test
	void shouldDoNothing_whenNoEmailIsConfigured() {
		// when
		initializer("", null).run(null);

		// then
		verifyNoInteractions(userRepository, passwordEncoder);
	}

	@Test
	void shouldRefuseToStart_whenPasswordIsTooShort() {
		assertThatThrownBy(() -> initializer("admin@example.com", "short").run(null))
			.isInstanceOf(IllegalStateException.class);
		verifyNoInteractions(userRepository);
	}

}
