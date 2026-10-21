package com.enervision.common.security;

import org.jspecify.annotations.NonNull;
import org.jspecify.annotations.Nullable;
import org.springframework.core.MethodParameter;
import org.springframework.security.authentication.AuthenticationCredentialsNotFoundException;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.bind.support.WebDataBinderFactory;
import org.springframework.web.context.request.NativeWebRequest;
import org.springframework.web.method.support.HandlerMethodArgumentResolver;
import org.springframework.web.method.support.ModelAndViewContainer;

import java.util.Set;
import java.util.UUID;
import java.util.stream.Collectors;

/**
 * Builds the {@link CurrentUser} from the Spring Security authentication: its name is the user id (JWT subject)
 * and its role authority gives the {@link Role}. Independent of how the request was authenticated.
 */
class CurrentUserArgumentResolver implements HandlerMethodArgumentResolver {

	@Override
	public boolean supportsParameter(MethodParameter parameter) {
		return parameter.getParameterType().equals(CurrentUser.class);
	}

	@Override
	public CurrentUser resolveArgument(@NonNull MethodParameter parameter, @Nullable ModelAndViewContainer mavContainer,
			@NonNull NativeWebRequest webRequest, @Nullable WebDataBinderFactory binderFactory) {
		Authentication authentication = SecurityContextHolder.getContext().getAuthentication();
		if (authentication == null || !authentication.isAuthenticated()) {
			throw new AuthenticationCredentialsNotFoundException("No authenticated user");
		}
		return new CurrentUser(UUID.fromString(authentication.getName()), toRole(authentication));
	}

	/** ADMIN takes precedence if both role authorities are present. */
	private static Role toRole(Authentication authentication) {
		Set<String> authorities = authentication.getAuthorities().stream()
			.map(GrantedAuthority::getAuthority)
			.collect(Collectors.toSet());
		if (authorities.contains(Role.ADMIN.authority())) {
			return Role.ADMIN;
		}
		if (authorities.contains(Role.USER.authority())) {
			return Role.USER;
		}
		throw new AuthenticationCredentialsNotFoundException("Authenticated user has no role");
	}

}
