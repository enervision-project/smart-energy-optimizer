package com.enervision.user.security;

import com.enervision.user.repository.UserRepository;
import lombok.RequiredArgsConstructor;
import org.jspecify.annotations.NonNull;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
@RequiredArgsConstructor
class DatabaseUserDetailsService implements UserDetailsService {

	private final UserRepository userRepository;

	@Override
	@Transactional(readOnly = true)
	public UserDetails loadUserByUsername(@NonNull String email) {
		return userRepository.findByEmail(email)
			.map(user -> org.springframework.security.core.userdetails.User.withUsername(user.getEmail())
				.password(user.getPassword())
				.roles(user.getRole().name())
				.build())
			.orElseThrow(() -> new UsernameNotFoundException("User not found"));
	}

}
