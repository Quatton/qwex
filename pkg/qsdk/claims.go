package qsdk

import (
	"fmt"
	"strconv"

	"github.com/golang-jwt/jwt/v5"
)

type UserClaims struct {
	ID    string
	Login string
	Name  string
	Email string
	Iss   string
	Iat   int64
	Exp   int64
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

func ParseUserFromToken(tokenStr string) (*UserClaims, error) {
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

	return uc, nil
}
