package connect

import (
	"bytes"
	"context"
	"errors"
	"io"
	"log"

	corev1 "k8s.io/api/core/v1"
	"k8s.io/client-go/kubernetes/scheme"
	"k8s.io/client-go/tools/remotecommand"
)

type Output struct {
	Stdout string
	Stderr string
}

func (s *Service) RemoteExec(ctx context.Context, cmd []string, stdin io.Reader) (*Output, error) {
	if s.Client == nil || s.Config == nil {
		return nil, errors.New("kubernetes client or config is not initialized")
	}

	req := s.Client.CoreV1().RESTClient().Post().
		Resource("pods").
		Name(s.PodName).
		Namespace(s.Namespace).
		SubResource("exec")

	option := &corev1.PodExecOptions{
		Container: s.ContainerName,
		Command:   cmd,
		Stdin:     stdin != nil,
		Stdout:    true,
		Stderr:    true,
		TTY:       false,
	}

	req.VersionedParams(
		option,
		scheme.ParameterCodec,
	)

	exec, err := remotecommand.NewSPDYExecutor(s.Config, "POST", req.URL())

	if err != nil {
		log.Printf("failed to create SPDY executor: %v", err)
		return nil, err
	}

	var stdout, stderr bytes.Buffer
	err = exec.StreamWithContext(ctx, remotecommand.StreamOptions{
		Stdin:  stdin,
		Stdout: &stdout,
		Stderr: &stderr,
		Tty:    false,
	})

	if err != nil {
		log.Printf("remote exec stream failed: %v", err)
		return nil, err
	}

	return &Output{
		Stdout: stdout.String(),
		Stderr: stderr.String(),
	}, nil
}
