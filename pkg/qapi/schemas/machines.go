package schemas

type MachineResponse struct {
	Body struct {
		MachineID string  `json:"machine_id" doc:"Unique identifier for the machine"`
		Status    string  `json:"status" doc:"Current status of the machine" enum:"creating,starting,running,stopping,stopped"`
		UserID    *string `json:"user_id,omitempty" doc:"ID of the user who owns the machine"`
	}
}

type ListMachinesResponse struct {
	Body struct {
		Machines []struct {
			MachineID string `json:"machine_id"`
			Status    string `json:"status"`
		} `json:"machines"`
	}
}
