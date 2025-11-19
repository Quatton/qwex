package schemas

// RefreshTokenRequest represents the payload for requesting a new access token.
type RefreshTokenRequest struct {
	Body struct {
		RefreshToken string `json:"refresh_token" doc:"Refresh token issued from login or previous refresh"`
	}
}

// RefreshTokenResponse contains a newly minted access token and refresh token.
type RefreshTokenResponse struct {
	Body struct {
		AccessToken  string `json:"access_token" doc:"New short-lived access token"`
		RefreshToken string `json:"refresh_token" doc:"Rotated refresh token"`
		TokenType    string `json:"token_type" doc:"Token type descriptor" example:"bearer"`
		ExpiresIn    int    `json:"expires_in" doc:"Access token lifetime in seconds"`
	}
}
