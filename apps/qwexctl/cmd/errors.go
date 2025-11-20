package cmd

import (
	"github.com/quatton/qwex/pkg/qerr"
	"github.com/quatton/qwex/pkg/qlog"
)

// exitIfSdkError inspects errors returned from the SDK and emits user-friendly
// guidance before exiting. Non-SDK errors fall back to logger.Fatal.
func exitIfSdkError(err error) {
	if err == nil {
		return
	}
	logger := qlog.NewDefault()

	switch {
	case qerr.IsCode(err, qerr.CodeUnauthorized):
		logger.Fatal("authentication required: run 'qwexctl auth login'", "error", err)
	case qerr.IsCode(err, qerr.CodeRefreshFailed):
		logger.Fatal("failed to refresh credentials: run 'qwexctl auth login'", "error", err)
	default:
		logger.Fatal("command failed", "error", err)
	}
}
