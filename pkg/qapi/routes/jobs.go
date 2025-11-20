package routes

import (
	"context"
	"fmt"
	"net/http"
	"time"

	"github.com/danielgtaylor/huma/v2"
	"github.com/quatton/qwex/pkg/qapi/schemas"
	"github.com/quatton/qwex/pkg/qrunner"
)

// SubmitJobInput defines the input for job submission
type SubmitJobInput struct {
	Body schemas.SubmitJobRequest
}

// SubmitJobOutput is the response for submitting a job
type SubmitJobOutput struct {
	Body schemas.JobResponse
}

// GetJobInput defines the input for getting a job
type GetJobInput struct {
	JobID string `path:"jobId" doc:"Job ID"`
}

// GetJobOutput is the response for getting a job
type GetJobOutput struct {
	Body schemas.JobResponse
}

// CancelJobInput defines the input for canceling a job
type CancelJobInput struct {
	JobID string `path:"jobId" doc:"Job ID"`
}

// ListJobsInput defines the input for listing jobs
type ListJobsInput struct {
	Status string `query:"status" doc:"Filter by status" required:"false"`
}

// ListJobsOutput is the response for listing jobs
type ListJobsOutput struct {
	Body struct {
		Jobs []schemas.JobResponse `json:"jobs" doc:"List of jobs"`
	}
}

// RegisterJobs registers job-related routes
func RegisterJobs(api huma.API, jobRunner qrunner.Runner) {
	// Submit job
	huma.Register(api, huma.Operation{
		OperationID: "submit-job",
		Method:      http.MethodPost,
		Path:        "/api/jobs",
		Summary:     "Submit a new job",
		Description: "Submit a job for execution",
		Tags:        []string{"Jobs"},
	}, func(ctx context.Context, input *SubmitJobInput) (*SubmitJobOutput, error) {
		// Validate required fields
		if input.Body.Name == "" {
			return nil, huma.Error400BadRequest("name is required")
		}
		if input.Body.Command == "" {
			return nil, huma.Error400BadRequest("command is required")
		}

		// Create job spec
		spec := qrunner.JobSpec{
			Name:       input.Body.Name,
			Command:    input.Body.Command,
			Args:       input.Body.Args,
			Env:        input.Body.Env,
			WorkingDir: input.Body.WorkingDir,
		}

		// Submit the job
		run, err := jobRunner.Submit(ctx, spec)
		if err != nil {
			return nil, huma.Error500InternalServerError(fmt.Sprintf("failed to submit job: %v", err))
		}

		resp := &SubmitJobOutput{
			Body: runToJobResponse(run),
		}
		return resp, nil
	})

	// List jobs
	huma.Register(api, huma.Operation{
		OperationID: "list-jobs",
		Method:      http.MethodGet,
		Path:        "/api/jobs",
		Summary:     "List jobs",
		Description: "Get a list of all jobs",
		Tags:        []string{"Jobs"},
	}, func(ctx context.Context, input *ListJobsInput) (*ListJobsOutput, error) {
		var status *qrunner.RunStatus
		if input.Status != "" {
			s := qrunner.RunStatus(input.Status)
			status = &s
		}

		runs, err := jobRunner.ListRuns(ctx, status)
		if err != nil {
			return nil, huma.Error500InternalServerError(fmt.Sprintf("failed to list jobs: %v", err))
		}

		// Convert to response
		jobs := make([]schemas.JobResponse, len(runs))
		for i, run := range runs {
			jobs[i] = runToJobResponse(run)
		}

		resp := &ListJobsOutput{}
		resp.Body.Jobs = jobs
		return resp, nil
	})

	// Get job
	huma.Register(api, huma.Operation{
		OperationID: "get-job",
		Method:      http.MethodGet,
		Path:        "/api/jobs/{jobId}",
		Summary:     "Get job details",
		Description: "Get details of a specific job",
		Tags:        []string{"Jobs"},
	}, func(ctx context.Context, input *GetJobInput) (*GetJobOutput, error) {
		if input.JobID == "" {
			return nil, huma.Error400BadRequest("job ID is required")
		}

		run, err := jobRunner.GetRun(ctx, input.JobID)
		if err != nil {
			return nil, huma.Error404NotFound(fmt.Sprintf("job not found: %v", err))
		}

		resp := &GetJobOutput{
			Body: runToJobResponse(run),
		}
		return resp, nil
	})

	// Cancel job
	huma.Register(api, huma.Operation{
		OperationID: "cancel-job",
		Method:      http.MethodDelete,
		Path:        "/api/jobs/{jobId}",
		Summary:     "Cancel a job",
		Description: "Cancel a running job",
		Tags:        []string{"Jobs"},
	}, func(ctx context.Context, input *CancelJobInput) (*struct{}, error) {
		if input.JobID == "" {
			return nil, huma.Error400BadRequest("job ID is required")
		}

		err := jobRunner.Cancel(ctx, input.JobID)
		if err != nil {
			return nil, huma.Error500InternalServerError(fmt.Sprintf("failed to cancel job: %v", err))
		}

		return &struct{}{}, nil
	})
}

// Helper function to convert Run to JobResponse
func runToJobResponse(run *qrunner.Run) schemas.JobResponse {
	resp := schemas.JobResponse{
		ID:        run.ID,
		Name:      run.JobID,
		Status:    string(run.Status),
		Command:   run.Command,
		Args:      run.Args,
		CreatedAt: run.CreatedAt.Format(time.RFC3339),
		ExitCode:  run.ExitCode,
		Error:     run.Error,
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

	return resp
}
