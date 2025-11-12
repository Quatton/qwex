package machines

import (
	"context"
	"fmt"

	corev1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/client-go/kubernetes"
	"k8s.io/client-go/rest"
	"k8s.io/client-go/tools/clientcmd"
)

const (
	DefaultNamespace = "qwex-machines"
	DefaultImage     = "ghcr.io/astral-sh/uv:0.9.8-bookworm-slim"
	LabelApp         = "qwex-machine"
	LabelMachineID   = "machine-id"
)

// Service handles machine (pod) operations
type Service struct {
	clientset *kubernetes.Clientset
	namespace string
}

func NewService() (*Service, error) {
	config, err := rest.InClusterConfig()
	if err != nil {
		loadingRules := clientcmd.NewDefaultClientConfigLoadingRules()
		configOverrides := &clientcmd.ConfigOverrides{}
		kubeConfig := clientcmd.NewNonInteractiveDeferredLoadingClientConfig(loadingRules, configOverrides)
		config, err = kubeConfig.ClientConfig()
		if err != nil {
			return nil, fmt.Errorf("failed to load kubeconfig: %w", err)
		}
	}

	clientset, err := kubernetes.NewForConfig(config)
	if err != nil {
		return nil, fmt.Errorf("failed to create kubernetes client: %w", err)
	}

	return &Service{
		clientset: clientset,
		namespace: DefaultNamespace,
	}, nil
}

func (s *Service) CreateMachine(ctx context.Context, machineID string) error {
	if err := s.ensureNamespace(ctx); err != nil {
		return fmt.Errorf("failed to ensure namespace: %w", err)
	}

	pod := &corev1.Pod{
		ObjectMeta: metav1.ObjectMeta{
			Name:      fmt.Sprintf("qwex-machine-%s", machineID),
			Namespace: s.namespace,
			Labels: map[string]string{
				LabelApp:       LabelApp,
				LabelMachineID: machineID,
			},
		},
		Spec: corev1.PodSpec{
			RestartPolicy: corev1.RestartPolicyNever,
			Containers: []corev1.Container{
				{
					Name:  "machine",
					Image: DefaultImage,
					Command: []string{
						"/bin/sh",
						"-c",
						"echo 'Machine started' && sleep infinity",
					},
				},
			},
		},
	}

	_, err := s.clientset.CoreV1().Pods(s.namespace).Create(ctx, pod, metav1.CreateOptions{})
	if err != nil {
		return fmt.Errorf("failed to create pod: %w", err)
	}

	return nil
}

func (s *Service) DeleteMachine(ctx context.Context, machineID string) error {
	podName := fmt.Sprintf("qwex-machine-%s", machineID)
	err := s.clientset.CoreV1().Pods(s.namespace).Delete(ctx, podName, metav1.DeleteOptions{})
	if err != nil {
		return fmt.Errorf("failed to delete pod: %w", err)
	}
	return nil
}

func (s *Service) GetMachineStatus(ctx context.Context, machineID string) (string, error) {
	podName := fmt.Sprintf("qwex-machine-%s", machineID)
	pod, err := s.clientset.CoreV1().Pods(s.namespace).Get(ctx, podName, metav1.GetOptions{})
	if err != nil {
		return "", fmt.Errorf("failed to get pod: %w", err)
	}

	switch pod.Status.Phase {
	case corev1.PodPending:
		return "starting", nil
	case corev1.PodRunning:
		return "running", nil
	case corev1.PodSucceeded, corev1.PodFailed:
		return "stopped", nil
	default:
		return "unknown", nil
	}
}

func (s *Service) ensureNamespace(ctx context.Context) error {
	_, err := s.clientset.CoreV1().Namespaces().Get(ctx, s.namespace, metav1.GetOptions{})
	if err == nil {
		return nil
	}

	ns := &corev1.Namespace{
		ObjectMeta: metav1.ObjectMeta{
			Name: s.namespace,
		},
	}
	_, err = s.clientset.CoreV1().Namespaces().Create(ctx, ns, metav1.CreateOptions{})
	if err != nil {
		return fmt.Errorf("failed to create namespace: %w", err)
	}
	return nil
}
