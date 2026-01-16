package pods

import "github.com/Quatton/qwex/apps/qwexctl/internal/k8s"

type Service struct {
	K8s *k8s.K8sClient
}

func NewService(k8sClient *k8s.K8sClient) *Service {
	return &Service{
		K8s: k8sClient,
	}
}
