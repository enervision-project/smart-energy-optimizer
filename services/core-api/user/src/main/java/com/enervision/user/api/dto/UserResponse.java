package com.enervision.user.api.dto;

import com.enervision.user.entities.Role;

import java.time.Instant;
import java.util.UUID;

public record UserResponse(
		UUID id,
		String email,
		String firstName,
		String lastName,
		String companyName,
		Role role,
		Instant createdAt,
		Instant updatedAt) {
}
