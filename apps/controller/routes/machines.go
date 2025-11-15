package routes

import (
	"context"
	"fmt"

	"github.com/danielgtaylor/huma/v2"
	"github.com/google/uuid"
)

// MachineResponse represents a machine response
type MachineResponse struct {
	Body struct {
		MachineID string `json:"machine_id" doc:"Unique identifier for the machine"`
		Status    string `json:"status" doc:"Current status of the machine" enum:"creating,starting,running,stopping,stopped"`
	}
}

func RegisterMachines(api huma.API) {
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

	machineID := uuid.New().String()
	fmt.Printf("Created machine: %s\n", machineID)

	resp := &MachineResponse{}
	resp.Body.MachineID = machineID
	resp.Body.Status = "creating"
	return resp, nil
}

func handleDeleteMachine(ctx context.Context, input *struct {
	MachineID string `path:"machine_id" doc:"The machine ID to delete" format:"uuid"`
}) (*MachineResponse, error) {

	fmt.Printf("Deleted machine: %s\n", input.MachineID)

	resp := &MachineResponse{}
	resp.Body.MachineID = input.MachineID
	resp.Body.Status = "stopped"
	return resp, nil
}
