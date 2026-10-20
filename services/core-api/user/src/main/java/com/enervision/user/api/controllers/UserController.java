package com.enervision.user.api.controllers;

import com.enervision.user.api.dto.UpdateRoleRequest;
import com.enervision.user.api.dto.UserResponse;
import com.enervision.user.security.AdminOnly;
import com.enervision.user.service.UserService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;
import java.util.Objects;
import java.util.UUID;

@RestController
@RequestMapping("/api/v1/users")
@RequiredArgsConstructor
@Tag(name = "Users")
public class UserController {

	private final UserService userService;

	@GetMapping("/me")
	@Operation(summary = "Get the current user's profile")
	public UserResponse getCurrentUser(@AuthenticationPrincipal Jwt jwt) {
		return userService.getUser(UUID.fromString(Objects.requireNonNull(jwt.getSubject())));
	}

	@GetMapping
	@AdminOnly
	@Operation(summary = "List users")
	public List<UserResponse> getUsers() {
		return userService.getUsers();
	}

	@GetMapping("/{userId}")
	@AdminOnly
	@Operation(summary = "Get a user")
	public UserResponse getUser(@PathVariable UUID userId) {
		return userService.getUser(userId);
	}

	@PatchMapping("/{userId}/role")
	@AdminOnly
	@Operation(summary = "Change a user's role")
	public UserResponse updateRole(@PathVariable UUID userId, @Valid @RequestBody UpdateRoleRequest request) {
		return userService.updateRole(userId, request.role());
	}

}
