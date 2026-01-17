package connect

import (
	"bytes"
	"context"
	"errors"
	"io"

	corev1 "k8s.io/api/core/v1"
	"k8s.io/client-go/kubernetes/scheme"
	"k8s.io/client-go/tools/remotecommand"
)

type Output struct {
	Stdout string
	Stderr string
}

func (s *Service) RemoteExec(ctx context.Context, cmd []string, stdin io.Reader) (*Output, error) {
	return s.RemoteExecContainer(ctx, cmd, stdin, s.ContainerName)
}

func (s *Service) RemoteExecContainer(ctx context.Context, cmd []string, stdin io.Reader, containerName string) (*Output, error) {
	if s.Client == nil || s.Config == nil {
		return nil, errors.New("kubernetes client or config is not initialized")
	}

	req := s.Client.CoreV1().RESTClient().Post().
		Resource("pods").
		Name(s.PodName).
		Namespace(s.Namespace).
		SubResource("exec")

	option := &corev1.PodExecOptions{
		Container: containerName,
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
		return &Output{
			Stdout: stdout.String(),
			Stderr: stderr.String(),
		}, err
	}

	return &Output{
		Stdout: stdout.String(),
		Stderr: stderr.String(),
	}, nil
}
