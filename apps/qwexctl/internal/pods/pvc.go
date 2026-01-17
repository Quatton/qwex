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

func (s *Service) GetOrCreatePVC(ctx context.Context) (*corev1.PersistentVolumeClaim, error) {
	pvcName := MakePVCName(s.Namespace)

	pvc, err := s.K8s.CoreV1().PersistentVolumeClaims(s.Namespace).Get(ctx, pvcName, metav1.GetOptions{})

	pvcSpec := &corev1.PersistentVolumeClaim{
		ObjectMeta: metav1.ObjectMeta{
			Name:      pvcName,
			Namespace: s.Namespace,
		},
		Spec: corev1.PersistentVolumeClaimSpec{
			AccessModes: []corev1.PersistentVolumeAccessMode{
				corev1.ReadWriteOnce,
			},
			Resources: corev1.VolumeResourceRequirements{
				Requests: corev1.ResourceList{
					corev1.ResourceStorage: resource.MustParse("2Gi"),
				},
				Limits: corev1.ResourceList{
					corev1.ResourceStorage: resource.MustParse("10Gi"),
				},
			},
		},
	}

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
