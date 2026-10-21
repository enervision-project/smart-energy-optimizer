package com.enervision.user.service;

import com.enervision.common.security.Role;
import com.enervision.user.api.dto.UserResponse;

import java.util.List;
import java.util.UUID;

public interface UserService {

	UserResponse getUser(UUID userId);

	List<UserResponse> getUsers();

	UserResponse updateRole(UUID userId, Role role);

}
