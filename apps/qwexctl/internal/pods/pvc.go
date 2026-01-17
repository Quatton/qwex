package pods

import (
	"context"
	"fmt"

	corev1 "k8s.io/api/core/v1"
	k8serrors "k8s.io/apimachinery/pkg/api/errors"
	"k8s.io/apimachinery/pkg/api/resource"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
)

func shouldPatchPVC(existing, desired *corev1.PersistentVolumeClaim) bool {
	existingStorage := existing.Spec.Resources.Requests[corev1.ResourceStorage]
	desiredStorage := desired.Spec.Resources.Requests[corev1.ResourceStorage]

	return existingStorage.Cmp(desiredStorage) < 0
}

func createPVCSpec(
	namespace, suffix string,
	storageSize string) *corev1.PersistentVolumeClaim {
	pvcSpec := &corev1.PersistentVolumeClaim{
		ObjectMeta: metav1.ObjectMeta{
			Name:      fmt.Sprintf("%s-%s", namespace, suffix),
			Namespace: namespace,
		},
		Spec: corev1.PersistentVolumeClaimSpec{
			AccessModes: []corev1.PersistentVolumeAccessMode{
				corev1.ReadWriteOnce,
			},
			Resources: corev1.VolumeResourceRequirements{
				Requests: corev1.ResourceList{
					corev1.ResourceStorage: resource.MustParse(storageSize),
				},
			},
		},
	}
	return pvcSpec
}

func (s *Service) GetOrCreatePVC(ctx context.Context,
	pvcSpec *corev1.PersistentVolumeClaim,
) (*corev1.PersistentVolumeClaim, error) {
	pvcName := pvcSpec.Name

	if pvcName == "" {
		return nil, fmt.Errorf("PVC spec must have a name")
	}

	pvc, err := s.K8s.CoreV1().PersistentVolumeClaims(s.Namespace).Get(ctx, pvcName, metav1.GetOptions{})

	if err != nil {
		if !k8serrors.IsNotFound(err) {
			return nil, fmt.Errorf("failed to get PVC %s: %w", pvcName, err)
		} else {
			createdPVC, err := s.K8s.CoreV1().PersistentVolumeClaims(s.Namespace).Create(ctx, pvcSpec, metav1.CreateOptions{})

			if err != nil {
				return nil, fmt.Errorf("failed to create PVC %s: %w", pvcName, err)
			}

			return createdPVC, nil
		}
	}

	if shouldPatchPVC(pvc, pvcSpec) {
		pvc.Spec.Resources = pvcSpec.Spec.Resources
		pvc.Namespace = s.Namespace
		pvc.Name = pvcName
		updatedPVC, err := s.K8s.CoreV1().PersistentVolumeClaims(s.Namespace).Update(ctx, pvc, metav1.UpdateOptions{})
		if err != nil {
			return nil, fmt.Errorf("failed to update PVC %s: %w", pvcName, err)
		}
		return updatedPVC, nil
	}
	return pvc, nil

}
