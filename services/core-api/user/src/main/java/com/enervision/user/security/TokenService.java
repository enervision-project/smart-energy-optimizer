package com.enervision.user.security;

import com.enervision.user.api.dto.TokenResponse;
import com.enervision.user.entity.User;

/**
 * Issues access tokens.
 */
public interface TokenService {

	TokenResponse generateToken(User user);

}
