package com.enervision.user.service;

import com.enervision.user.api.dto.LoginRequest;
import com.enervision.user.api.dto.TokenResponse;

public interface AuthService {

	TokenResponse login(LoginRequest request);

}
