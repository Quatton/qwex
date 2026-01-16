package pods

import (
	"context"
	"testing"
	"time"

	"github.com/Quatton/qwex/apps/qwexctl/internal/k8s"
)

const testNamespace = "qwex-demo"

func TestMakeDeploymentName(t *testing.T) {
	expected := "qwex-demo-dev"
	actual := makeDevelopmentName(testNamespace)
	if actual != expected {
		panic("makeDevelopmentName did not return expected value")
	}
}

func TestCreateDevPod(t *testing.T) {
	ctx, cancel := context.WithTimeout(t.Context(), 10*time.Minute)
	defer cancel()

	k8sClient, err := k8s.NewK8sClient()
	if err != nil {
		t.Fatalf("Expected no error creating k8s client, got %v", err)
	}

	service := NewService(k8sClient.Clientset, testNamespace)

	res, err := service.GetOrCreateDevelopmentDeployment(ctx, Active)

	if err != nil {
		t.Fatalf("Expected no error creating dev pod, got %v", err)
	}

	t.Logf("Created/Retrieved dev pod: %s", res.Name)

	if res.Name != makeDevelopmentName(testNamespace) {
		t.Fatalf("Expected pod name %s, got %s", makeDevelopmentName(testNamespace), res.Name)
	}

	for _, c := range res.Status.Conditions {
		t.Logf("Condition: %s - %s", c.Type, c.Status)
	}

	desiredReplicas := *res.Spec.Replicas

	if res.Status.ReadyReplicas < desiredReplicas {
		t.Fatalf("Should wait for all replicas to be ready")
	}
}

func TestDestroyDevPod(t *testing.T) {
	k8sClient, err := k8s.NewK8sClient()
	if err != nil {
		t.Fatalf("Expected no error creating k8s client, got %v", err)
	}
	service := Service{
		K8s: k8sClient.Clientset,
	}

	err = service.DestroyDevelopment(t.Context(), testNamespace)

	if err != nil {
		t.Fatalf("Expected no error destroying dev pod, got %v", err)
	}

	t.Logf("Destroyed dev pod in namespace: %s", testNamespace)
}
