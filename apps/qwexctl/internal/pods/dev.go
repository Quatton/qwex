package pods

import (
	"context"
	"fmt"
	"log"
	"time"

	"github.com/Quatton/qwex/apps/qwexctl/internal/k8s"
	appsv1 "k8s.io/api/apps/v1"
	corev1 "k8s.io/api/core/v1"
	k8serrors "k8s.io/apimachinery/pkg/api/errors"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/util/wait"
)

type Service struct {
	K8s *k8s.K8sClient
}

func NewService(k8sClient *k8s.K8sClient) *Service {
	return &Service{
		K8s: k8sClient,
	}
}

// TODO: Move to config
const (
	DemoImage             = "ghcr.io/astral-sh/uv:0.9.13-python3.12-bookworm"
	PodTypeLabel          = "qwex.dev/pod-type"
	PodTypeDevelopment    = "development"
	DevelopmentDeployment = "dev"
)

func makeDevelopmentName(namespace string) string {
	return fmt.Sprintf("%s-%s", namespace, DevelopmentDeployment)
}

func (s *Service) GetOrCreateDevelopmentDeployment(ctx context.Context, namespace string) (*appsv1.Deployment, error) {
	name := makeDevelopmentName(namespace)

	existing, err := s.K8s.Clientset.AppsV1().Deployments(namespace).Get(ctx, name, metav1.GetOptions{})
	if err == nil {
		return existing, s.waitForDeploymentReady(ctx, namespace, name)
	}
	if !k8serrors.IsNotFound(err) {
		return nil, fmt.Errorf("failed to check existing deployment: %w", err)
	}

	replica := int32(1)

	dep := &appsv1.Deployment{
		ObjectMeta: metav1.ObjectMeta{
			Name: name,
			Labels: map[string]string{
				PodTypeLabel: PodTypeDevelopment,
			},
		},
		Spec: appsv1.DeploymentSpec{
			Replicas: &replica,
			Selector: &metav1.LabelSelector{
				MatchLabels: map[string]string{
					PodTypeLabel: PodTypeDevelopment,
					"app":        "dev",
				},
			},
			Template: corev1.PodTemplateSpec{
				ObjectMeta: metav1.ObjectMeta{
					Labels: map[string]string{
						PodTypeLabel: PodTypeDevelopment,
						"app":        "dev",
					},
				},
				Spec: corev1.PodSpec{
					RestartPolicy: corev1.RestartPolicyAlways,
					Containers: []corev1.Container{
						{
							Name:            "devcontainer",
							Image:           DemoImage,
							ImagePullPolicy: corev1.PullIfNotPresent,
							Command:         []string{"/bin/sh", "-c", "tail -f /dev/null"},
						},
					},
				},
			},
		},
	}

	created, err := s.K8s.Clientset.AppsV1().Deployments(namespace).Create(ctx, dep, metav1.CreateOptions{})
	if err != nil {
		return nil, fmt.Errorf("failed to create deployment: %w", err)
	}

	log.Printf("Development deployment %s created, waiting for ready...", name)
	return created, s.waitForDeploymentReady(ctx, namespace, name)
}

func (s *Service) waitForDeploymentReady(ctx context.Context, namespace, name string) error {
	return wait.PollUntilContextTimeout(ctx, 2*time.Second, 5*time.Minute, true, func(ctx context.Context) (bool, error) {
		dep, err := s.K8s.Clientset.AppsV1().Deployments(namespace).Get(ctx, name, metav1.GetOptions{})
		if err != nil {
			return false, err
		}

		for _, cond := range dep.Status.Conditions {
			if cond.Type == appsv1.DeploymentAvailable && cond.Status == corev1.ConditionTrue {
				log.Printf("Deployment %s is ready", name)
				return true, nil
			}
		}

		return false, nil
	})
}

func (s *Service) DestroyDevelopment(ctx context.Context, namespace string) error {
	name := makeDevelopmentName(namespace)
	prop := metav1.DeletePropagationBackground

	err := s.K8s.Clientset.AppsV1().Deployments(namespace).Delete(ctx, name, metav1.DeleteOptions{
		PropagationPolicy: &prop,
	})

	if err != nil && !k8serrors.IsNotFound(err) {
		return err
	}
	return nil
}
