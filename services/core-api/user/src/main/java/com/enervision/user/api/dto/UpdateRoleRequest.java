package com.enervision.user.api.dto;

import com.enervision.user.entities.Role;
import jakarta.validation.constraints.NotNull;

public record UpdateRoleRequest(
		@NotNull Role role) {
}
