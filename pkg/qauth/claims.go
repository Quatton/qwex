package qauth

import (
	"fmt"
	"strconv"
	"time"

	"github.com/golang-jwt/jwt/v5"
)

// UserClaims represents a minimal, CLI-friendly view of the JWT payload.
// Important: this is intended for display and UX only when parsed without
// verification. Do not use these values for security decisions unless the
// token has been cryptographically verified by a trusted key.
type UserClaims struct {
	ID          string
	Login       string
	Name        string
	Email       string
	GithubID    string
	GithubLogin string
	Iss         string
	Aud         string
	Iat         int64
	Exp         int64
}

// ParseTokenClaims extracts raw claims from a JWT without verifying its
// signature. This is useful for clients that need to inspect token payloads
// but do not possess the issuer's signing key. The returned MapClaims will
// contain numeric timestamps as float64 per the jwt library behavior.
// WARNING: do not rely on this for authorization.
func ParseTokenClaims(tokenStr string) (jwt.MapClaims, error) {
	var claims jwt.MapClaims
	parser := new(jwt.Parser)
	_, _, err := parser.ParseUnverified(tokenStr, &claims)
	if err != nil {
		return nil, err
	}
	return claims, nil
}

func FromToken(tokenStr string) (*UserClaims, error) {
	claims, err := ParseTokenClaims(tokenStr)
	if err != nil {
		return nil, err
	}
	return FromMapClaims(claims)
}

// FromMapClaims reads token claims (without verification) and maps them into a
// stable UserClaims structure. It tolerates both string and numeric forms of
// the `sub`, `iat`, and `exp` claims and normalizes them into strings/int64s.
// Use this when you need a predictable programmatic representation of a
// token's user payload for display or tooling.
func FromMapClaims(mc jwt.MapClaims) (*UserClaims, error) {
	uc := &UserClaims{}

	if sub, ok := mc["sub"]; ok {
		switch v := sub.(type) {
		case string:
			uc.ID = v
		case float64:
			uc.ID = strconv.FormatInt(int64(v), 10)
		default:
			uc.ID = fmt.Sprintf("%v", v)
		}
	}

	if login, ok := mc["login"].(string); ok {
		uc.Login = login
	}
	if name, ok := mc["name"].(string); ok {
		uc.Name = name
	}
	if email, ok := mc["email"].(string); ok {
		uc.Email = email
	}
	if iss, ok := mc["iss"].(string); ok {
		uc.Iss = iss
	}

	if iat, ok := mc["iat"]; ok {
		switch v := iat.(type) {
		case float64:
			uc.Iat = int64(v)
		case int64:
			uc.Iat = v
		}
	}

	if exp, ok := mc["exp"]; ok {
		switch v := exp.(type) {
		case float64:
			uc.Exp = int64(v)
		case int64:
			uc.Exp = v
		}
	}

	if gid, ok := mc["github_id"]; ok {
		switch v := gid.(type) {
		case string:
			uc.GithubID = v
		case float64:
			uc.GithubID = strconv.FormatInt(int64(v), 10)
		default:
			uc.GithubID = fmt.Sprintf("%v", v)
		}
	}

	if gl, ok := mc["github_login"].(string); ok {
		uc.GithubLogin = gl
	}

	if aud, ok := mc["aud"].(string); ok {
		uc.Aud = aud
	}

	return uc, nil
}

// ToClaims converts a UserClaims into jwt.MapClaims suitable for signing by
// the server. It intentionally keeps fields flat (e.g. `github_id`) so the
// token remains compact and compatible with existing clients. Numeric
// timestamp fields must be set by the caller (iat/exp) in unix seconds.
func ToClaims(uc *UserClaims) jwt.MapClaims {
	mc := jwt.MapClaims{}
	if uc.ID != "" {
		mc["sub"] = uc.ID
	}
	if uc.Login != "" {
		mc["login"] = uc.Login
	}
	if uc.Name != "" {
		mc["name"] = uc.Name
	}
	if uc.Email != "" {
		mc["email"] = uc.Email
	}
	if uc.GithubID != "" {
		mc["github_id"] = uc.GithubID
	}
	if uc.GithubLogin != "" {
		mc["github_login"] = uc.GithubLogin
	}
	if uc.Iss != "" {
		mc["iss"] = uc.Iss
	}
	if uc.Iat != 0 {
		mc["iat"] = uc.Iat
	}
	if uc.Exp != 0 {
		mc["exp"] = uc.Exp
	}
	if uc.Aud != "" {
		mc["aud"] = uc.Aud
	}
	return mc
}

// IsTokenExpired returns true when the access token is expired or within the
// provided skew window. It relies on FromToken to parse the JWT without
// verifying the signature, which is sufficient for local UX decisions.
func IsTokenExpired(token string, skew time.Duration) (bool, error) {
	if token == "" {
		return true, nil
	}
	uc, err := FromToken(token)
	if err != nil {
		return true, err
	}
	if uc.Exp == 0 {
		return false, nil
	}
	expiresAt := time.Unix(uc.Exp, 0).Add(-skew)
	return time.Now().After(expiresAt), nil
}
