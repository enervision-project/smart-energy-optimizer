package com.enervision.user.security;

import com.enervision.common.security.Role;
import com.enervision.user.entity.User;
import com.enervision.user.repository.UserRepository;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UsernameNotFoundException;

import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class DatabaseUserDetailsServiceTest {

	@Mock
	private UserRepository userRepository;

	@InjectMocks
	private DatabaseUserDetailsService userDetailsService;

	@Test
	void shouldLoadUserWithRole_whenEmailExists() {
		// given
		User user = new User();
		user.setEmail("jane@example.com");
		user.setPassword("{bcrypt}hash");
		user.setRole(Role.ADMIN);
		when(userRepository.findByEmail("jane@example.com")).thenReturn(Optional.of(user));

		// when
		UserDetails details = userDetailsService.loadUserByUsername("jane@example.com");

		// then
		assertThat(details.getUsername()).isEqualTo("jane@example.com");
		assertThat(details.getPassword()).isEqualTo("{bcrypt}hash");
		assertThat(details.getAuthorities()).extracting(GrantedAuthority::getAuthority).containsExactly("ROLE_ADMIN");
	}

	@Test
	void shouldThrowUsernameNotFound_whenEmailIsUnknown() {
		// given
		when(userRepository.findByEmail("unknown@example.com")).thenReturn(Optional.empty());

		// when / then
		assertThatThrownBy(() -> userDetailsService.loadUserByUsername("unknown@example.com"))
			.isInstanceOf(UsernameNotFoundException.class);
	}

}
