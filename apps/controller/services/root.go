package services

import (
	"github.com/quatton/qwex/apps/controller/services/iam"
	"github.com/quatton/qwex/apps/controller/services/machines"
)

type Container struct {
	Machines *machines.MachinesService
	IAM      *iam.IAMService
}
