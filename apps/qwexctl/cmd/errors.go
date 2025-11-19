package cmd

import (
	"log"

	"github.com/quatton/qwex/pkg/qerr"
)

// exitIfSdkError inspects errors returned from the SDK and emits user-friendly
// guidance before exiting. Non-SDK errors fall back to log.Fatalf.
func exitIfSdkError(err error) {
	if err == nil {
		return
	}
	switch {
	case qerr.IsCode(err, qerr.CodeUnauthorized):
		log.Fatalf("authentication required: run 'qwexctl auth login' (%v)", err)
	case qerr.IsCode(err, qerr.CodeRefreshFailed):
		log.Fatalf("failed to refresh credentials: run 'qwexctl auth login' (%v)", err)
	default:
		log.Fatalf("%v", err)
	}
}
