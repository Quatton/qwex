package qsdk

import (
	"fmt"
	"strconv"

	"github.com/golang-jwt/jwt/v5"
)

type UserClaims struct {
	ID          string
	Login       string
	Name        string
	Email       string
	GithubID    string
	GithubLogin string
	Iss         string
	Iat         int64
	Exp         int64
}

func ParseTokenClaims(tokenStr string) (jwt.MapClaims, error) {
	var claims jwt.MapClaims
	parser := new(jwt.Parser)
	_, _, err := parser.ParseUnverified(tokenStr, &claims)
	if err != nil {
		return nil, err
	}
	return claims, nil
}

func FromClaims(tokenStr string) (*UserClaims, error) {
	mc, err := ParseTokenClaims(tokenStr)
	if err != nil {
		return nil, err
	}

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

	return uc, nil
}

// ToClaims converts UserClaims into jwt.MapClaims suitable for signing.
func ToClaims(uc *UserClaims) jwt.MapClaims {
	mc := jwt.MapClaims{}
	if uc.ID != "" {
		// sub can be string
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
	return mc
}
