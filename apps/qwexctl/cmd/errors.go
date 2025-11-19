package cmd

import (
	"log"

	sdkerrors "github.com/quatton/qwex/pkg/qsdk/qerr"
)

// exitIfSdkError inspects errors returned from the SDK and emits user-friendly
// guidance before exiting. Non-SDK errors fall back to log.Fatalf.
func exitIfSdkError(err error) {
	if err == nil {
		return
	}
	switch {
	case sdkerrors.IsCode(err, sdkerrors.CodeUnauthorized):
		log.Fatalf("authentication required: run 'qwexctl auth login' (%v)", err)
	case sdkerrors.IsCode(err, sdkerrors.CodeRefreshFailed):
		log.Fatalf("failed to refresh credentials: run 'qwexctl auth login' (%v)", err)
	default:
		log.Fatalf("%v", err)
	}
}
