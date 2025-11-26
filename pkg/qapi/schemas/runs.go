package schemas

// SubmitRunRequest represents a request to submit a run
type SubmitRunRequest struct {
	Name       string            `json:"name,omitempty" doc:"Run name (optional)"`
	Backend    string            `json:"backend,omitempty" doc:"Backend to use (local, docker, k8s). Defaults to local"`
	Command    string            `json:"command" doc:"Command to execute"`
	Args       []string          `json:"args,omitempty" doc:"Command arguments"`
	Env        map[string]string `json:"env,omitempty" doc:"Environment variables"`
	WorkingDir string            `json:"working_dir,omitempty" doc:"Working directory"`
	Image      string            `json:"image,omitempty" doc:"Container image (for docker/k8s backends)"`
}

// RunArtifact represents a stored artifact for a run
type RunArtifact struct {
	Key         string `json:"key" doc:"Storage key"`
	Filename    string `json:"filename" doc:"Original filename"`
	Size        int64  `json:"size" doc:"Size in bytes"`
	ContentType string `json:"content_type" doc:"MIME type"`
	URL         string `json:"url,omitempty" doc:"Download URL (presigned)"`
}

// RunResponse represents a run execution result
type RunResponse struct {
	ID         string            `json:"id" doc:"Run ID"`
	Name       string            `json:"name,omitempty" doc:"Run name"`
	Backend    string            `json:"backend" doc:"Backend used (local, docker, k8s)"`
	Status     string            `json:"status" doc:"Run status"`
	Command    string            `json:"command" doc:"Command"`
	Args       []string          `json:"args,omitempty" doc:"Command arguments"`
	CreatedAt  string            `json:"created_at" doc:"Creation timestamp"`
	StartedAt  *string           `json:"started_at,omitempty" doc:"Start timestamp"`
	FinishedAt *string           `json:"finished_at,omitempty" doc:"Finish timestamp"`
	ExitCode   *int              `json:"exit_code,omitempty" doc:"Exit code"`
	Metadata   map[string]string `json:"metadata,omitempty" doc:"Additional metadata"`
	Artifacts  []RunArtifact     `json:"artifacts,omitempty" doc:"Run artifacts"`
}
