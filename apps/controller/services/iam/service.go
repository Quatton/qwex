package iam

import (
	"github.com/quatton/qwex/apps/controller/services/authconfig"
)

type IAMService struct {
	auth *authconfig.AuthService
}

func NewIAMService(auth *authconfig.AuthService) *IAMService {
	return &IAMService{auth: auth}
}
