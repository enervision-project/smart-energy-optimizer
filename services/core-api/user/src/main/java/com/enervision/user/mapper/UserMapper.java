package com.enervision.user.mapper;

import com.enervision.user.api.dto.RegisterRequest;
import com.enervision.user.api.dto.UserResponse;
import com.enervision.user.domain.User;
import org.springframework.stereotype.Component;

@Component
public class UserMapper {

	public UserResponse toResponse(User user) {
		return new UserResponse(
				user.getId(),
				user.getEmail(),
				user.getFirstName(),
				user.getLastName(),
				user.getCompanyName(),
				user.getRole(),
				user.getCreatedAt(),
				user.getUpdatedAt());
	}

	/**
	 * Copies the profile fields. The normalized email, password hash and role are set by the service.
	 */
	public User toEntity(RegisterRequest request) {
		User user = new User();
		user.setFirstName(request.firstName().trim());
		user.setLastName(request.lastName().trim());
		user.setCompanyName(request.companyName().trim());
		return user;
	}

}
