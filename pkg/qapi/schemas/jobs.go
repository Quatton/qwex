package schemas

// SubmitJobRequest represents a request to submit a job
type SubmitJobRequest struct {
	Name       string            `json:"name" doc:"Job name"`
	Command    string            `json:"command" doc:"Command to execute"`
	Args       []string          `json:"args,omitempty" doc:"Command arguments"`
	Env        map[string]string `json:"env,omitempty" doc:"Environment variables"`
	WorkingDir string            `json:"working_dir,omitempty" doc:"Working directory"`
}

// JobResponse represents a job execution result
type JobResponse struct {
	ID         string            `json:"id" doc:"Job ID"`
	Name       string            `json:"name" doc:"Job name"`
	Status     string            `json:"status" doc:"Job status"`
	Command    string            `json:"command" doc:"Command"`
	Args       []string          `json:"args,omitempty" doc:"Command arguments"`
	CreatedAt  string            `json:"created_at" doc:"Creation timestamp"`
	StartedAt  *string           `json:"started_at,omitempty" doc:"Start timestamp"`
	FinishedAt *string           `json:"finished_at,omitempty" doc:"Finish timestamp"`
	ExitCode   *int              `json:"exit_code,omitempty" doc:"Exit code"`
	Error      string            `json:"error,omitempty" doc:"Error message if failed"`
	Metadata   map[string]string `json:"metadata,omitempty" doc:"Additional metadata"`
}
