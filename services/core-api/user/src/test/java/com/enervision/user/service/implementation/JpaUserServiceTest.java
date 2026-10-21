package com.enervision.user.service.implementation;

import com.enervision.user.api.dto.UserResponse;
import com.enervision.user.entity.Role;
import com.enervision.user.entity.User;
import com.enervision.user.exception.UserNotFoundException;
import com.enervision.user.mapper.UserMapper;
import com.enervision.user.repository.UserRepository;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.Spy;
import org.mockito.junit.jupiter.MockitoExtension;

import java.util.Optional;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.AdditionalAnswers.returnsFirstArg;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class JpaUserServiceTest {

	@Mock
	private UserRepository userRepository;

	@Spy
	private UserMapper userMapper = new UserMapper();

	@InjectMocks
	private JpaUserService userService;

	@Test
	void shouldThrowUserNotFound_whenUserDoesNotExist() {
		// given
		UUID userId = UUID.randomUUID();
		when(userRepository.findById(userId)).thenReturn(Optional.empty());

		// when / then
		assertThatThrownBy(() -> userService.getUser(userId)).isInstanceOf(UserNotFoundException.class);
	}

	@Test
	void shouldUpdateRole_whenUserExists() {
		// given
		UUID userId = UUID.randomUUID();
		User user = new User();
		user.setId(userId);
		user.setRole(Role.USER);
		when(userRepository.findById(userId)).thenReturn(Optional.of(user));
		when(userRepository.saveAndFlush(user)).then(returnsFirstArg());

		// when
		UserResponse response = userService.updateRole(userId, Role.ADMIN);

		// then
		assertThat(response.role()).isEqualTo(Role.ADMIN);
	}

}
