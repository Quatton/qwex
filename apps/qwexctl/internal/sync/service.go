package sync

import (
	"k8s.io/client-go/kubernetes"
	"k8s.io/client-go/rest"
)

type Service struct {
	Client    kubernetes.Interface
	Config    *rest.Config
	Namespace string
	PodName   string
	Container string
}
