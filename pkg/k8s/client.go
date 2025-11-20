package k8s

import (
	"os"
	"path/filepath"

	"k8s.io/client-go/kubernetes"
	"k8s.io/client-go/rest"
	"k8s.io/client-go/tools/clientcmd"
)

// NewClient creates a new Kubernetes clientset
// It first tries in-cluster config (service account), then falls back to kubeconfig
func NewClient() (*kubernetes.Clientset, error) {
	config, err := GetConfig()
	if err != nil {
		return nil, err
	}
	return kubernetes.NewForConfig(config)
}

// GetConfig returns a Kubernetes REST config
// Priority: in-cluster config > KUBECONFIG env > ~/.kube/config
func GetConfig() (*rest.Config, error) {
	// Try in-cluster config first (when running in a pod)
	if config, err := rest.InClusterConfig(); err == nil {
		return config, nil
	}

	// Fall back to kubeconfig file
	kubeconfig := os.Getenv("KUBECONFIG")
	if kubeconfig == "" {
		// Use default kubeconfig location
		home, err := os.UserHomeDir()
		if err != nil {
			return nil, err
		}
		kubeconfig = filepath.Join(home, ".kube", "config")
	}

	return clientcmd.BuildConfigFromFlags("", kubeconfig)
}
