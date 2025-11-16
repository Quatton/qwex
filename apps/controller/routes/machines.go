package routes

import (
	"context"

	"github.com/danielgtaylor/huma/v2"
	"github.com/quatton/qwex/apps/controller/schemas"
	"github.com/quatton/qwex/apps/controller/services/machines"
)

func RegisterMachines(api huma.API, svc *machines.MachinesService) {
	huma.Register(api, huma.Operation{
		OperationID: "create-machine",
		Method:      "POST",
		Path:        "/api/machines",
		Summary:     "Create a new machine",
		Description: "Creates and starts a new machine (pod) with the uv image",
		Tags:        []string{"Machines"},
		Security:    BearerAuth,
	}, func(ctx context.Context, input *struct{}) (*schemas.MachineResponse, error) {
		return svc.Create(ctx, input)
	})

	huma.Register(api, huma.Operation{
		OperationID: "delete-machine",
		Method:      "DELETE",
		Path:        "/api/machines/{machine_id}",
		Summary:     "Delete a machine",
		Description: "Stops and deletes a machine (pod) and all associated resources",
		Tags:        []string{"Machines"},
		Security:    BearerAuth,
	}, func(ctx context.Context, input *struct {
		MachineID string `path:"machine_id" doc:"The machine ID to delete" format:"uuid"`
	}) (*schemas.MachineResponse, error) {
		return svc.Delete(ctx, input)
	})

	huma.Register(api, huma.Operation{
		OperationID: "list-machines",
		Method:      "GET",
		Path:        "/api/machines",
		Summary:     "List user's machines",
		Description: "List all machines owned by the authenticated user",
		Tags:        []string{"Machines"},
		Security:    BearerAuth,
	}, func(ctx context.Context, input *struct{}) (*schemas.ListMachinesResponse, error) {
		return svc.List(ctx, input)
	})
}
