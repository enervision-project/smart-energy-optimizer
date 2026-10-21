package com.enervision.user.service.implementation;

import com.enervision.user.api.dto.UserResponse;
import com.enervision.user.entity.Role;
import com.enervision.user.entity.User;
import com.enervision.user.exception.UserNotFoundException;
import com.enervision.user.mapper.UserMapper;
import com.enervision.user.repository.UserRepository;
import com.enervision.user.service.UserService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;
import java.util.UUID;

@Slf4j
@Service
@RequiredArgsConstructor
@Transactional(readOnly = true)
class JpaUserService implements UserService {

	private final UserRepository userRepository;
	private final UserMapper userMapper;

	@Override
	public UserResponse getUser(UUID userId) {
		return userMapper.toResponse(findUser(userId));
	}

	@Override
	public List<UserResponse> getUsers() {
		return userRepository.findAll().stream()
			.map(userMapper::toResponse)
			.toList();
	}

	@Override
	@Transactional
	public UserResponse updateRole(UUID userId, Role role) {
		User user = findUser(userId);
		user.setRole(role);
		log.info("Role of user {} changed to {}", userId, role);
		// flush so that updatedAt is up to date in the response
		return userMapper.toResponse(userRepository.saveAndFlush(user));
	}

	private User findUser(UUID userId) {
		return userRepository.findById(userId)
			.orElseThrow(() -> new UserNotFoundException(userId));
	}

}
