package pods

import (
	"context"
	"fmt"
	"log"
	"time"

	appsv1 "k8s.io/api/apps/v1"
	corev1 "k8s.io/api/core/v1"
	k8serrors "k8s.io/apimachinery/pkg/api/errors"
	"k8s.io/apimachinery/pkg/api/resource"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/util/wait"
	"k8s.io/client-go/util/retry"
)

type DevelopmentMode string

const (
	Active    DevelopmentMode = "active"
	Hibernate DevelopmentMode = "hibernate"
)

func makeContainers(mode DevelopmentMode) []corev1.Container {
	containers := []corev1.Container{
		{
			Name:            SyncContainerName,
			Image:           SyncImage,
			ImagePullPolicy: corev1.PullIfNotPresent,
			Command: []string{
				"/bin/sh",
				"-c",
				"tail -f /dev/null",
			},
			VolumeMounts: []corev1.VolumeMount{
				{
					Name:      WorkspaceVolumeName,
					MountPath: WorkspaceMountPath,
				},
			},
			Resources: corev1.ResourceRequirements{
				Requests: corev1.ResourceList{
					corev1.ResourceCPU:    resource.MustParse("100m"),
					corev1.ResourceMemory: resource.MustParse("256Mi"),
				},
			},
		},
	}

	if mode == Active {
		devContainer := corev1.Container{

			Name:            DevContainerName,
			Image:           DevelopmentDemoImage,
			ImagePullPolicy: corev1.PullIfNotPresent,
			Command:         []string{"/bin/sh", "-c", "tail -f /dev/null"},
			VolumeMounts: []corev1.VolumeMount{
				{
					Name:      WorkspaceVolumeName,
					MountPath: WorkspaceMountPath,
				},
			},
			Resources: corev1.ResourceRequirements{
				Requests: corev1.ResourceList{
					corev1.ResourceCPU:    resource.MustParse("100m"),
					corev1.ResourceMemory: resource.MustParse("512Mi"),
				},
				Limits: corev1.ResourceList{
					corev1.ResourceCPU:    resource.MustParse("2000m"),
					corev1.ResourceMemory: resource.MustParse("4Gi"),
				},
			},
		}

		containers = append(containers, devContainer)
	}

	return containers
}

func (s *Service) buildDesiredDeployment(namespace string, mode DevelopmentMode) *appsv1.Deployment {
	name := makeDevelopmentName(namespace)
	replica := int32(1)

	dep := &appsv1.Deployment{
		ObjectMeta: metav1.ObjectMeta{
			Name: name,
			Labels: map[string]string{
				PodTypeLabel: DevelopmentTypeLabel,
			},
		},
		Spec: appsv1.DeploymentSpec{
			Replicas: &replica,
			Selector: &metav1.LabelSelector{
				MatchLabels: map[string]string{
					PodTypeLabel: DevelopmentTypeLabel,
				},
			},
			Strategy: appsv1.DeploymentStrategy{
				Type: appsv1.RecreateDeploymentStrategyType,
			},
			Template: corev1.PodTemplateSpec{
				ObjectMeta: metav1.ObjectMeta{
					Labels: map[string]string{
						PodTypeLabel: DevelopmentTypeLabel,
					},
				},
				Spec: corev1.PodSpec{
					Volumes: []corev1.Volume{
						{
							Name: WorkspaceVolumeName,
							VolumeSource: corev1.VolumeSource{
								PersistentVolumeClaim: &corev1.PersistentVolumeClaimVolumeSource{
									ClaimName: makePVCName(namespace),
								},
							},
						},
					},
					InitContainers: []corev1.Container{
						{
							Name:            InitContainerName,
							Image:           SyncImage,
							ImagePullPolicy: corev1.PullIfNotPresent,
							Command: []string{
								"/bin/sh",
								"-c",
								// TODO: This is hardcoded for demo purposes
								"if [ ! -d /workspace/.git ]; then git init /workspace; echo 'Repo initialized'; else echo 'Repo exists'; fi",
							},
							VolumeMounts: []corev1.VolumeMount{
								{
									Name:      WorkspaceVolumeName,
									MountPath: WorkspaceMountPath,
								},
							},
						},
					},
					RestartPolicy: corev1.RestartPolicyAlways,
					Containers:    makeContainers(mode),
				},
			},
		},
	}

	return dep
}

func (s *Service) GetOrCreateDevelopmentDeployment(ctx context.Context, namespace string) (*appsv1.Deployment, error) {

	// Ensure PVC exists
	_, err := s.GetOrCreatePVC(ctx, namespace)

	if err != nil {
		return nil, fmt.Errorf("failed to ensure PVC exists in namespace %s: %w", namespace, err)
	}

	// TODO: Hibernate mode support
	desired := s.buildDesiredDeployment(namespace, Active)

	var current *appsv1.Deployment

	name := makeDevelopmentName(namespace)

	err = retry.RetryOnConflict(retry.DefaultRetry, func() error {
		current, getErr := s.K8s.Clientset.AppsV1().Deployments(namespace).Get(ctx, name, metav1.GetOptions{})
		if getErr != nil {
			if k8serrors.IsNotFound(getErr) {
				created, createErr := s.K8s.Clientset.AppsV1().Deployments(namespace).Create(ctx, desired, metav1.CreateOptions{})
				if createErr != nil {
					return createErr
				}
				current = created
				return nil
			}
			return getErr
		}

		desired.ResourceVersion = current.ResourceVersion
		updated, updateErr := s.K8s.Clientset.AppsV1().Deployments(namespace).Update(ctx, desired, metav1.UpdateOptions{})
		if updateErr != nil {
			return updateErr
		}
		current = updated
		return nil
	})

	if err != nil {
		return nil, fmt.Errorf("failed to reconcile deployment %s: %w", name, err)
	}

	log.Printf("Development deployment %s reconciled, waiting for ready...", name)
	return current, s.waitForDeploymentReady(ctx, namespace, name)
}

func (s *Service) waitForDeploymentReady(ctx context.Context, namespace, name string) error {
	const interval = 2 * time.Second
	const timeout = 5 * time.Minute

	log.Printf("Waiting for a Ready pod in deployment %s/%s...", namespace, name)

	return wait.PollUntilContextTimeout(ctx, interval, timeout, true, func(ctx context.Context) (bool, error) {
		dep, err := s.K8s.Clientset.AppsV1().Deployments(namespace).Get(ctx, name, metav1.GetOptions{})

		if err != nil {
			return false, err
		}

		loggedObservedGeneration := false
		loggedUpdatedReplicas := false
		loggedReadyReplicas := false

		if dep.Generation > dep.Status.ObservedGeneration && !loggedObservedGeneration {
			log.Printf("Deployment %s/%s not observed yet (generation %d > observed %d)", namespace, name, dep.Generation, dep.Status.ObservedGeneration)
			return false, nil
		}

		desiredReplicas := *dep.Spec.Replicas

		if dep.Status.UpdatedReplicas < desiredReplicas && !loggedUpdatedReplicas {
			log.Printf("Deployment %s/%s updating replicas: %d/%d", namespace, name, dep.Status.UpdatedReplicas, desiredReplicas)
			loggedUpdatedReplicas = true
			return false, nil
		}

		if dep.Status.ReadyReplicas < desiredReplicas && !loggedReadyReplicas {
			log.Printf("Deployment %s/%s ready replicas: %d/%d", namespace, name, dep.Status.ReadyReplicas, desiredReplicas)
			loggedReadyReplicas = true
			return false, nil
		}

		log.Printf("Deployment %s/%s is ready with %d/%d replicas", namespace, name, dep.Status.ReadyReplicas, desiredReplicas)
		return true, nil
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
