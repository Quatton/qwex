package pods

import (
	"k8s.io/client-go/kubernetes"
)

type Service struct {
	K8s       kubernetes.Interface
	Namespace string
}

func NewService(k8sClient kubernetes.Interface, namespace string) *Service {
	return &Service{
		K8s:       k8sClient,
		Namespace: namespace,
	}
}
