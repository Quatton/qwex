package k8s

import (
	"testing"

	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
)

func TestNewK8sClient_LocalFallback(t *testing.T) {
	client, err := NewK8sClient()
	if err != nil {
		t.Fatalf("Expected no error, got %v", err)
	}

	ctx := t.Context()
	res, err := client.Clientset.CoreV1().Namespaces().List(ctx, metav1.ListOptions{})
	if err != nil {
		t.Fatalf("Expected no error listing namespaces, got %v", err)
	}

	for _, ns := range res.Items {
		t.Logf("Found namespace: %s", ns.Name)
	}
}
