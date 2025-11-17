package qsdk

import (
	"reflect"
	"testing"

	"github.com/golang-jwt/jwt/v5"
)

func TestFromClaimsRoundTrip(t *testing.T) {
	uc := &UserClaims{
		ID:          "123",
		Login:       "alice",
		Name:        "Alice",
		Email:       "alice@example.com",
		GithubID:    "999",
		GithubLogin: "aliceGH",
		Iss:         "qwex",
		Iat:         1000,
		Exp:         2000,
	}

	claims := ToClaims(uc)

	token := jwt.NewWithClaims(jwt.SigningMethodHS256, claims)

	tokenStr, err := token.SignedString([]byte("test-secret"))
	if err != nil {
		t.Fatalf("failed to sign token: %v", err)
	}

	parsed, err := FromToken(tokenStr)
	if err != nil {
		t.Fatalf("FromClaims error: %v", err)
	}

	if !reflect.DeepEqual(parsed, uc) {
		t.Fatalf("parsed claims mismatch\nexpected=%#v\nparsed=%#v", uc, parsed)
	}
}

func TestFromMapClaimsHandlesNumericSub(t *testing.T) {
	mc := jwt.MapClaims{
		"sub":          float64(42),
		"login":        "bob",
		"name":         "Bob",
		"email":        "bob@example.com",
		"github_id":    float64(7),
		"github_login": "bobGH",
		"iss":          "qwex",
		"iat":          float64(1600),
		"exp":          float64(2600),
	}

	uc, err := FromMapClaims(mc)
	if err != nil {
		t.Fatalf("FromMapClaims error: %v", err)
	}

	if uc.ID != "42" {
		t.Fatalf("expected ID 42 got %s", uc.ID)
	}
	if uc.GithubID != "7" {
		t.Fatalf("expected GithubID 7 got %s", uc.GithubID)
	}
	if uc.Login != "bob" || uc.GithubLogin != "bobGH" {
		t.Fatalf("unexpected login fields: %+v", uc)
	}
}

func TestToClaimsOmitsEmpty(t *testing.T) {
	uc := &UserClaims{ID: "1", Login: "x"}
	mc := ToClaims(uc)
	if _, ok := mc["name"]; ok {
		t.Fatalf("expected name to be omitted when empty")
	}
	if mc["sub"] != "1" {
		t.Fatal("expected sub to be set to ", uc.ID)
	}
}
