package iam

import (
	"github.com/go-pkgz/auth"
)

type IAMService struct {
	auth *auth.Service
}

func NewIAMService(auth *auth.Service) *IAMService {
	return &IAMService{auth: auth}
}
