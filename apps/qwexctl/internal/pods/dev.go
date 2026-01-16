package pods

import (
	"context"
	"fmt"
	"log"
	"time"

	"github.com/Quatton/qwex/apps/qwexctl/internal/k8s"
	corev1 "k8s.io/api/core/v1"
	k8serrors "k8s.io/apimachinery/pkg/api/errors"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/util/wait"
)

// TODO: Move to config
const (
	DemoImage          = "ghcr.io/astral-sh/uv:0.9.13-python3.12-bookworm"
	PodTypeLabel       = "qwex.dev/pod-type"
	PodTypeDevelopment = "development"
)

type Service struct {
	K8s *k8s.K8sClient
}

func NewService(k8sClient *k8s.K8sClient) *Service {
	return &Service{
		K8s: k8sClient,
	}
}

/*
GetOrCreateDevelopmentPod ensures a running development pod exists.
1. Checks if it exists.
2. If it exists but is dead (Failed/Succeeded), deletes it.
3. If it doesn't exist, creates it.
4. Waits for it to be Running.
*/
func (s *Service) GetOrCreateDevelopmentPod(ctx context.Context, namespace string) (*corev1.Pod, error) {
	podName := makeDevelopmentPodName(namespace)

	existingPod, err := s.K8s.Clientset.CoreV1().Pods(namespace).Get(ctx, podName, metav1.GetOptions{})

	if err == nil {
		if existingPod.Status.Phase == corev1.PodSucceeded || existingPod.Status.Phase == corev1.PodFailed {
			log.Printf("Found dead pod %s (Phase: %s), recreating...", podName, existingPod.Status.Phase)
			if err := s.DestroyDevelopmentPod(ctx, namespace); err != nil {
				return nil, fmt.Errorf("failed to clean up dead pod: %w", err)
			}
		} else {
			return s.waitForPodRunning(ctx, namespace, podName)
		}
	} else if !k8serrors.IsNotFound(err) {
		return nil, fmt.Errorf("failed to check existing pod: %w", err)
	}

	return s.createDevelopmentPod(ctx, namespace)
}

/*
createDevelopmentPod constructs the pod manifest and submits it.
*/
func (s *Service) createDevelopmentPod(ctx context.Context, namespace string) (*corev1.Pod, error) {
	podName := makeDevelopmentPodName(namespace)

	pod := &corev1.Pod{
		ObjectMeta: metav1.ObjectMeta{
			Name: podName,
			Labels: map[string]string{
				PodTypeLabel: PodTypeDevelopment,
			},
		},
		Spec: corev1.PodSpec{
			RestartPolicy: corev1.RestartPolicyOnFailure,
			Containers: []corev1.Container{
				{
					Name:            "dev-container",
					Image:           DemoImage,
					ImagePullPolicy: corev1.PullIfNotPresent,
					Command:         []string{"/bin/sh", "-c", "tail -f /dev/null"},
				},
			},
		},
	}

	_, err := s.K8s.Clientset.CoreV1().Pods(namespace).Create(ctx, pod, metav1.CreateOptions{})
	if err != nil {
		return nil, fmt.Errorf("failed to create pod: %w", err)
	}

	log.Printf("Development pod %s created, waiting for status Running...", podName)
	return s.waitForPodRunning(ctx, namespace, podName)
}

/*
waitForPodRunning blocks until the pod phase is Running.
Uses k8s.io/apimachinery/pkg/util/wait for robust polling.
*/
func (s *Service) waitForPodRunning(ctx context.Context, namespace, podName string) (*corev1.Pod, error) {
	var readyPod *corev1.Pod

	// Poll every 1 second, timeout after 5 minutes
	err := wait.PollUntilContextTimeout(ctx, 1*time.Second, 5*time.Minute, true, func(ctx context.Context) (bool, error) {
		p, err := s.K8s.Clientset.CoreV1().Pods(namespace).Get(ctx, podName, metav1.GetOptions{})
		if err != nil {
			// If pod disappears while waiting, stop and return error
			return false, err
		}

		if p.Status.Phase == corev1.PodRunning {
			readyPod = p
			return true, nil // Done
		}

		// Continue waiting if Pending/ContainerCreating
		return false, nil
	})

	if err != nil {
		return nil, fmt.Errorf("timed out waiting for pod %s to be running: %w", podName, err)
	}

	return readyPod, nil
}

func (s *Service) DestroyDevelopmentPod(ctx context.Context, namespace string) error {
	podName := makeDevelopmentPodName(namespace)
	// Use DeletePropagationBackground to ensure cleanup doesn't block needlessly
	prop := metav1.DeletePropagationBackground

	err := s.K8s.Clientset.CoreV1().Pods(namespace).Delete(ctx, podName, metav1.DeleteOptions{
		PropagationPolicy: &prop,
	})

	if err != nil && !k8serrors.IsNotFound(err) {
		return err
	}
	return nil
}

func makeDevelopmentPodName(namespace string) string {
	// Naming suggestion: Don't repeat the namespace in the name if possible,
	// but keeping your convention for now.
	return fmt.Sprintf("%s-dev-pod", namespace)
}
