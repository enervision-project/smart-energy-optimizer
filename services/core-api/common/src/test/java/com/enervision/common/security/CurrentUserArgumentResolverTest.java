package com.enervision.common.security;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.AuthenticationCredentialsNotFoundException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.authority.AuthorityUtils;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.context.request.NativeWebRequest;

import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.mock;

class CurrentUserArgumentResolverTest {

	private static final UUID USER_ID = UUID.randomUUID();

	private final CurrentUserArgumentResolver resolver = new CurrentUserArgumentResolver();

	private final NativeWebRequest request = mock(NativeWebRequest.class);

	@AfterEach
	void clearSecurityContext() {
		SecurityContextHolder.clearContext();
	}

	@Test
	void shouldResolveUser_whenAuthenticatedWithUserRole() {
		// given
		authenticate("ROLE_USER");

		// when
		CurrentUser currentUser = resolver.resolveArgument(null, null, request, null);

		// then
		assertThat(currentUser).isEqualTo(new CurrentUser(USER_ID, Role.USER));
		assertThat(currentUser.isAdmin()).isFalse();
	}

	@Test
	void shouldResolveAdmin_whenAuthenticatedWithAdminRole() {
		// given
		authenticate("ROLE_ADMIN");

		// when
		CurrentUser currentUser = resolver.resolveArgument(null, null, request, null);

		// then
		assertThat(currentUser.role()).isEqualTo(Role.ADMIN);
		assertThat(currentUser.isAdmin()).isTrue();
	}

	@Test
	void shouldThrow_whenNotAuthenticated() {
		assertThatThrownBy(() -> resolver.resolveArgument(null, null, request, null))
			.isInstanceOf(AuthenticationCredentialsNotFoundException.class);
	}

	@Test
	void shouldThrow_whenUserHasNoRole() {
		// given
		authenticate("SCOPE_read");

		// when / then
		assertThatThrownBy(() -> resolver.resolveArgument(null, null, request, null))
			.isInstanceOf(AuthenticationCredentialsNotFoundException.class);
	}

	private static void authenticate(String authority) {
		SecurityContextHolder.getContext().setAuthentication(UsernamePasswordAuthenticationToken.authenticated(
				USER_ID.toString(), null, AuthorityUtils.createAuthorityList(authority)));
	}

}
