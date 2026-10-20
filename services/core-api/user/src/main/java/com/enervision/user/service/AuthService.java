package com.enervision.user.service;

import com.enervision.user.api.dto.LoginRequest;
import com.enervision.user.api.dto.RegisterRequest;
import com.enervision.user.api.dto.TokenResponse;
import com.enervision.user.api.dto.UserResponse;

public interface AuthService {

	UserResponse register(RegisterRequest request);

	TokenResponse login(LoginRequest request);

}
