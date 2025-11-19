package runner

import (
	"context"
	"os"
	"path/filepath"

	"github.com/quatton/qwex/pkg/qsdk"
)

type LocalRunner struct {
	runsDir string
	outDir  string
}

func NewLocalRunner() *LocalRunner {
	cwd, _ := os.Getwd()
	return &LocalRunner{
		// TODO: make these configurable
		runsDir: filepath.Join(cwd, qsdk.ConfigRoot, "runs"),
		outDir:  filepath.Join(cwd, qsdk.ConfigRoot, "out"),
	}
}

func (r *LocalRunner) Run(ctx context.Context, spec JobSpec) error {
	return nil
}
