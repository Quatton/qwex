package machines

import (
	"context"
	"fmt"

	"github.com/google/uuid"
	"github.com/quatton/qwex/apps/controller/schemas"
	"github.com/quatton/qwex/apps/controller/services/iam"
)

type MachinesService struct {
	iam *iam.IAMService
}

func NewMachinesService(iamSvc *iam.IAMService) *MachinesService {
	return &MachinesService{iam: iamSvc}
}

func (s *MachinesService) Create(ctx context.Context, _ *struct{}) (*schemas.MachineResponse, error) {
	user := s.iam.Must(ctx)

	machineID := uuid.New().String()
	fmt.Printf("Created machine: %s for user: %s\n", machineID, user.ID)

	resp := &schemas.MachineResponse{}
	resp.Body.MachineID = machineID
	resp.Body.Status = "creating"
	resp.Body.UserID = &user.ID
	return resp, nil
}

func (s *MachinesService) Delete(ctx context.Context, input *struct {
	MachineID string `path:"machine_id" doc:"The machine ID to delete" format:"uuid"`
}) (*schemas.MachineResponse, error) {
	user := s.iam.Must(ctx)

	fmt.Printf("User %s deleting machine: %s\n", user.ID, input.MachineID)

	resp := &schemas.MachineResponse{}
	resp.Body.MachineID = input.MachineID
	resp.Body.Status = "stopped"
	resp.Body.UserID = &user.ID
	return resp, nil
}

func (s *MachinesService) List(ctx context.Context, _ *struct{}) (*schemas.ListMachinesResponse, error) {
	user := s.iam.Must(ctx)

	fmt.Printf("Listing machines for user: %s\n", user.ID)

	resp := &schemas.ListMachinesResponse{}
	resp.Body.Machines = []struct {
		MachineID string `json:"machine_id"`
		Status    string `json:"status"`
	}{
		{MachineID: "example-1", Status: "running"},
		{MachineID: "example-2", Status: "stopped"},
	}
	return resp, nil
}
