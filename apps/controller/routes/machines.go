package routes

import (
	"context"
	"fmt"

	"github.com/danielgtaylor/huma/v2"
	"github.com/google/uuid"
	"github.com/quatton/qwex/apps/controller/services/machines"
)

var machineService *machines.Service

// MachineResponse represents a machine response
type MachineResponse struct {
	Body struct {
		MachineID string `json:"machine_id" doc:"Unique identifier for the machine"`
		Status    string `json:"status" doc:"Current status of the machine" enum:"creating,starting,running,stopping,stopped"`
	}
}

func RegisterMachines(api huma.API) {
	var err error
	machineService, err = machines.NewService()
	if err != nil {
		fmt.Printf("Warning: Failed to initialize machine service: %v\n", err)
		fmt.Println("Machine endpoints will return errors until k8s is configured")
	}

	huma.Register(api, huma.Operation{
		OperationID: "create-machine",
		Method:      "POST",
		Path:        "/api/machines",
		Summary:     "Create a new machine",
		Description: "Creates and starts a new machine (pod) with the uv image",
		Tags:        []string{"Machines"},
	}, handleCreateMachine)

	huma.Register(api, huma.Operation{
		OperationID: "delete-machine",
		Method:      "DELETE",
		Path:        "/api/machines/{machine_id}",
		Summary:     "Delete a machine",
		Description: "Stops and deletes a machine (pod) and all associated resources",
		Tags:        []string{"Machines"},
	}, handleDeleteMachine)
}

func handleCreateMachine(ctx context.Context, input *struct{}) (*MachineResponse, error) {
	if machineService == nil {
		return nil, fmt.Errorf("machine service not initialized - kubernetes not configured")
	}

	machineID := uuid.New().String()
	err := machineService.CreateMachine(ctx, machineID)
	if err != nil {
		return nil, fmt.Errorf("failed to create machine: %w", err)
	}

	fmt.Printf("Created machine: %s\n", machineID)

	resp := &MachineResponse{}
	resp.Body.MachineID = machineID
	resp.Body.Status = "creating"
	return resp, nil
}

func handleDeleteMachine(ctx context.Context, input *struct {
	MachineID string `path:"machine_id" doc:"The machine ID to delete" format:"uuid"`
}) (*MachineResponse, error) {
	if machineService == nil {
		return nil, fmt.Errorf("machine service not initialized - kubernetes not configured")
	}

	err := machineService.DeleteMachine(ctx, input.MachineID)
	if err != nil {
		return nil, fmt.Errorf("failed to delete machine: %w", err)
	}

	fmt.Printf("Deleted machine: %s\n", input.MachineID)

	resp := &MachineResponse{}
	resp.Body.MachineID = input.MachineID
	resp.Body.Status = "stopped"
	return resp, nil
}
