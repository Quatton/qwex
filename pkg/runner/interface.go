package runner

import "context"

type RunSpec struct {
	ID         string
	Command    string
	CommitHash string
	RepoURL    string
	Env        map[string]string
}

type Runner interface {
	Run(ctx context.Context, spec RunSpec) error
}
