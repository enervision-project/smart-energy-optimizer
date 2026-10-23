package com.enervision.user.security;

import com.enervision.common.security.Role;
import com.enervision.user.entity.User;
import com.enervision.user.repository.UserRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.util.StringUtils;

import java.util.Locale;

/**
 * Creates the first administrator from {@link InitialAdminProperties} when no user exists yet, so that a new
 * environment can be logged into. Does nothing once a user exists: changing the properties afterwards has no effect.
 */
@Slf4j
@Component
@RequiredArgsConstructor
class InitialAdminInitializer implements ApplicationRunner {

	static final int MIN_PASSWORD_LENGTH = 12;

	private final InitialAdminProperties properties;
	private final UserRepository userRepository;
	private final PasswordEncoder passwordEncoder;

	@Override
	@Transactional
	public void run(ApplicationArguments args) {
		String email = properties.email();
		if (!StringUtils.hasText(email)) {
			return;
		}
		String password = properties.password();
		if (password == null || password.length() < MIN_PASSWORD_LENGTH) {
			throw new IllegalStateException("enervision.security.initial-admin.password must be at least "
					+ MIN_PASSWORD_LENGTH + " characters long");
		}
		if (userRepository.count() > 0) {
			return;
		}

		User admin = new User();
		admin.setEmail(email.trim().toLowerCase(Locale.ROOT));
		admin.setPassword(passwordEncoder.encode(password));
		admin.setFirstName("Admin");
		admin.setLastName("EnerVision");
		admin.setCompanyName("EnerVision");
		admin.setRole(Role.ADMIN);
		userRepository.save(admin);
		log.info("Initial administrator {} created", admin.getEmail());
	}

}
