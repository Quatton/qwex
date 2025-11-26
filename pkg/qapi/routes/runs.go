package routes

import (
	"context"
	"fmt"
	"io"
	"net/http"
	"path"
	"time"

	"github.com/danielgtaylor/huma/v2"
	"github.com/quatton/qwex/pkg/qapi/schemas"
	"github.com/quatton/qwex/pkg/qapi/services"
	"github.com/quatton/qwex/pkg/qart"
	"github.com/quatton/qwex/pkg/qrunner"
)

// SubmitRunInput defines the input for submitting a run
type SubmitRunInput struct {
	Body schemas.SubmitRunRequest
}

// SubmitRunOutput is the response for submitting a run
type SubmitRunOutput struct {
	Body schemas.RunResponse
}

// GetRunInput defines the input for getting a run
type GetRunInput struct {
	RunID string `path:"runId" doc:"Run ID"`
}

// GetRunOutput is the response for getting a run
type GetRunOutput struct {
	Body schemas.RunResponse
}

// CancelRunInput defines the input for canceling a run
type CancelRunInput struct {
	RunID string `path:"runId" doc:"Run ID"`
}

// ListRunsInput defines the input for listing runs
type ListRunsInput struct {
	Backend string `query:"backend" doc:"Filter by backend (local, docker, k8s)" required:"false"`
	Status  string `query:"status" doc:"Filter by status" required:"false"`
}

// ListRunsOutput is the response for listing runs
type ListRunsOutput struct {
	Body struct {
		Runs []schemas.RunResponse `json:"runs" doc:"List of runs"`
	}
}

// GetRunLogsInput defines the input for getting run logs
type GetRunLogsInput struct {
	RunID string `path:"runId" doc:"Run ID"`
}

// GetRunLogsOutput is the response for getting run logs
type GetRunLogsOutput struct {
	Body struct {
		Logs string `json:"logs" doc:"Run logs"`
	}
}

// ListRunArtifactsInput defines the input for listing run artifacts
type ListRunArtifactsInput struct {
	RunID string `path:"runId" doc:"Run ID"`
}

// ListRunArtifactsOutput is the response for listing run artifacts
type ListRunArtifactsOutput struct {
	Body struct {
		Artifacts []schemas.RunArtifact `json:"artifacts" doc:"List of artifacts"`
	}
}

// GetArtifactURLInput defines the input for getting an artifact presigned URL
type GetArtifactURLInput struct {
	RunID    string `path:"runId" doc:"Run ID"`
	Filename string `path:"filename" doc:"Artifact filename"`
}

// GetArtifactURLOutput is the response for getting an artifact presigned URL
type GetArtifactURLOutput struct {
	Body struct {
		URL string `json:"url" doc:"Presigned download URL"`
	}
}

// ListBackendsOutput is the response for listing enabled backends
type ListBackendsOutput struct {
	Body struct {
		Backends []string `json:"backends" doc:"List of enabled backends"`
	}
}

// RegisterRuns registers run-related routes
func RegisterRuns(api huma.API, runners *services.RunnerRegistry, s3Store qart.Store) {
	// List enabled backends
	huma.Register(api, huma.Operation{
		OperationID: "list-backends",
		Method:      http.MethodGet,
		Path:        "/api/backends",
		Summary:     "List enabled backends",
		Description: "Get a list of enabled runner backends",
		Tags:        []string{"Runs"},
	}, func(ctx context.Context, input *struct{}) (*ListBackendsOutput, error) {
		resp := &ListBackendsOutput{}
		if runners != nil {
			resp.Body.Backends = runners.EnabledBackends()
		} else {
			resp.Body.Backends = []string{}
		}
		return resp, nil
	})

	// Submit run
	huma.Register(api, huma.Operation{
		OperationID: "submit-run",
		Method:      http.MethodPost,
		Path:        "/api/runs",
		Summary:     "Submit a new run",
		Description: "Submit a job for execution on the specified backend",
		Tags:        []string{"Runs"},
	}, func(ctx context.Context, input *SubmitRunInput) (*SubmitRunOutput, error) {
		if runners == nil {
			return nil, huma.Error503ServiceUnavailable("no runners configured")
		}

		// Validate required fields
		if input.Body.Command == "" {
			return nil, huma.Error400BadRequest("command is required")
		}

		// Get the requested backend (default to local)
		backend := input.Body.Backend
		if backend == "" {
			backend = "local"
		}

		runner := runners.Get(backend)
		if runner == nil {
			return nil, huma.Error400BadRequest(fmt.Sprintf("backend '%s' is not enabled", backend))
		}

		// Create job spec
		spec := qrunner.JobSpec{
			Name:       input.Body.Name,
			Command:    input.Body.Command,
			Args:       input.Body.Args,
			Env:        input.Body.Env,
			WorkingDir: input.Body.WorkingDir,
			Image:      input.Body.Image,
		}

		// Submit the job
		run, err := runner.Submit(ctx, spec)
		if err != nil {
			return nil, huma.Error500InternalServerError(fmt.Sprintf("failed to submit run: %v", err))
		}

		resp := &SubmitRunOutput{
			Body: toRunResponse(run, backend),
		}
		return resp, nil
	})

	// List runs
	huma.Register(api, huma.Operation{
		OperationID: "list-runs",
		Method:      http.MethodGet,
		Path:        "/api/runs",
		Summary:     "List runs",
		Description: "Get a list of all runs",
		Tags:        []string{"Runs"},
	}, func(ctx context.Context, input *ListRunsInput) (*ListRunsOutput, error) {
		if runners == nil {
			return &ListRunsOutput{}, nil
		}

		var status *qrunner.RunStatus
		if input.Status != "" {
			s := qrunner.RunStatus(input.Status)
			status = &s
		}

		resp := &ListRunsOutput{}
		resp.Body.Runs = []schemas.RunResponse{}

		// If backend specified, only list from that backend
		if input.Backend != "" {
			runner := runners.Get(input.Backend)
			if runner != nil {
				runs, err := runner.ListRuns(ctx, status)
				if err == nil {
					for _, run := range runs {
						resp.Body.Runs = append(resp.Body.Runs, toRunResponse(run, input.Backend))
					}
				}
			}
			return resp, nil
		}

		// Otherwise, list from all backends
		for _, backend := range runners.EnabledBackends() {
			runner := runners.Get(backend)
			if runner != nil {
				runs, err := runner.ListRuns(ctx, status)
				if err == nil {
					for _, run := range runs {
						resp.Body.Runs = append(resp.Body.Runs, toRunResponse(run, backend))
					}
				}
			}
		}

		return resp, nil
	})

	// Get run
	huma.Register(api, huma.Operation{
		OperationID: "get-run",
		Method:      http.MethodGet,
		Path:        "/api/runs/{runId}",
		Summary:     "Get run details",
		Description: "Get details of a specific run",
		Tags:        []string{"Runs"},
	}, func(ctx context.Context, input *GetRunInput) (*GetRunOutput, error) {
		if runners == nil {
			return nil, huma.Error503ServiceUnavailable("no runners configured")
		}

		if input.RunID == "" {
			return nil, huma.Error400BadRequest("run ID is required")
		}

		// Try each backend until we find the run
		for _, backend := range runners.EnabledBackends() {
			runner := runners.Get(backend)
			if runner != nil {
				run, err := runner.GetRun(ctx, input.RunID)
				if err == nil && run != nil {
					return &GetRunOutput{Body: toRunResponse(run, backend)}, nil
				}
			}
		}

		return nil, huma.Error404NotFound("run not found")
	})

	// Cancel run
	huma.Register(api, huma.Operation{
		OperationID: "cancel-run",
		Method:      http.MethodDelete,
		Path:        "/api/runs/{runId}",
		Summary:     "Cancel a run",
		Description: "Cancel a running job",
		Tags:        []string{"Runs"},
	}, func(ctx context.Context, input *CancelRunInput) (*struct{}, error) {
		if runners == nil {
			return nil, huma.Error503ServiceUnavailable("no runners configured")
		}

		if input.RunID == "" {
			return nil, huma.Error400BadRequest("run ID is required")
		}

		// Try each backend until we find and cancel the run
		for _, backend := range runners.EnabledBackends() {
			runner := runners.Get(backend)
			if runner != nil {
				err := runner.Cancel(ctx, input.RunID)
				if err == nil {
					return &struct{}{}, nil
				}
			}
		}

		return nil, huma.Error404NotFound("run not found")
	})

	// Get run logs
	huma.Register(api, huma.Operation{
		OperationID: "get-run-logs",
		Method:      http.MethodGet,
		Path:        "/api/runs/{runId}/logs",
		Summary:     "Get run logs",
		Description: "Get logs from a run execution",
		Tags:        []string{"Runs"},
	}, func(ctx context.Context, input *GetRunLogsInput) (*GetRunLogsOutput, error) {
		if runners == nil {
			return nil, huma.Error503ServiceUnavailable("no runners configured")
		}

		if input.RunID == "" {
			return nil, huma.Error400BadRequest("run ID is required")
		}

		// Try each backend until we find the run
		for _, backend := range runners.EnabledBackends() {
			runner := runners.Get(backend)
			if runner != nil {
				reader, err := runner.GetLogs(ctx, input.RunID)
				if err == nil && reader != nil {
					defer reader.Close()
					logs, err := io.ReadAll(reader)
					if err != nil {
						return nil, huma.Error500InternalServerError(fmt.Sprintf("failed to read logs: %v", err))
					}
					return &GetRunLogsOutput{Body: struct {
						Logs string `json:"logs" doc:"Run logs"`
					}{Logs: string(logs)}}, nil
				}
			}
		}

		return nil, huma.Error404NotFound("run not found")
	})

	// List run artifacts
	huma.Register(api, huma.Operation{
		OperationID: "list-run-artifacts",
		Method:      http.MethodGet,
		Path:        "/api/runs/{runId}/artifacts",
		Summary:     "List run artifacts",
		Description: "List all artifacts from a run execution",
		Tags:        []string{"Runs"},
	}, func(ctx context.Context, input *ListRunArtifactsInput) (*ListRunArtifactsOutput, error) {
		if input.RunID == "" {
			return nil, huma.Error400BadRequest("run ID is required")
		}

		if s3Store == nil {
			return nil, huma.Error501NotImplemented("artifact storage not configured")
		}

		// List artifacts with the run prefix
		prefix := qart.RunArtifactPrefix(input.RunID)
		objects, err := s3Store.List(ctx, prefix)
		if err != nil {
			return nil, huma.Error500InternalServerError(fmt.Sprintf("failed to list artifacts: %v", err))
		}

		artifacts := make([]schemas.RunArtifact, 0, len(objects))
		for _, obj := range objects {
			// Extract filename from the key (e.g., "runs/abc123/stdout.log" -> "stdout.log")
			filename := path.Base(obj.Key)
			artifacts = append(artifacts, schemas.RunArtifact{
				Key:         obj.Key,
				Filename:    filename,
				Size:        obj.Size,
				ContentType: obj.ContentType,
			})
		}

		resp := &ListRunArtifactsOutput{}
		resp.Body.Artifacts = artifacts
		return resp, nil
	})

	// Get artifact download URL
	huma.Register(api, huma.Operation{
		OperationID: "get-artifact-url",
		Method:      http.MethodGet,
		Path:        "/api/runs/{runId}/artifacts/{filename}/url",
		Summary:     "Get artifact download URL",
		Description: "Get a presigned URL to download an artifact",
		Tags:        []string{"Runs"},
	}, func(ctx context.Context, input *GetArtifactURLInput) (*GetArtifactURLOutput, error) {
		if input.RunID == "" {
			return nil, huma.Error400BadRequest("run ID is required")
		}
		if input.Filename == "" {
			return nil, huma.Error400BadRequest("filename is required")
		}

		if s3Store == nil {
			return nil, huma.Error501NotImplemented("artifact storage not configured")
		}

		// Build the artifact key
		key := qart.RunArtifactKey(input.RunID, input.Filename)

		// Get presigned URL (valid for 1 hour)
		url, err := s3Store.GetPresignedURL(ctx, key, time.Hour)
		if err != nil {
			return nil, huma.Error500InternalServerError(fmt.Sprintf("failed to get presigned URL: %v", err))
		}

		resp := &GetArtifactURLOutput{}
		resp.Body.URL = url
		return resp, nil
	})
}

// toRunResponse converts a qrunner.Run to a schemas.RunResponse
func toRunResponse(run *qrunner.Run, backend string) schemas.RunResponse {
	resp := schemas.RunResponse{
		ID:        run.ID,
		Name:      run.Name,
		Backend:   backend,
		Status:    string(run.Status),
		Command:   run.Command,
		Args:      run.Args,
		CreatedAt: run.CreatedAt.Format(time.RFC3339),
		ExitCode:  run.ExitCode,
		Metadata:  run.Metadata,
	}

	if run.StartedAt != nil {
		startedAt := run.StartedAt.Format(time.RFC3339)
		resp.StartedAt = &startedAt
	}

	if run.FinishedAt != nil {
		finishedAt := run.FinishedAt.Format(time.RFC3339)
		resp.FinishedAt = &finishedAt
	}

	// Convert artifacts
	for _, a := range run.Artifacts {
		resp.Artifacts = append(resp.Artifacts, schemas.RunArtifact{
			Key:         a.Key,
			Filename:    a.Filename,
			Size:        a.Size,
			ContentType: a.ContentType,
			URL:         a.URL,
		})
	}

	return resp
}
