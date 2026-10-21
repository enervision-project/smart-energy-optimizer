package com.enervision.user.mapper;

import com.enervision.user.api.dto.UserResponse;
import com.enervision.user.entity.User;
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

}
