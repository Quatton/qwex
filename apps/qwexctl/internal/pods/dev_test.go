package pods

import (
	"testing"

	"github.com/Quatton/qwex/apps/qwexctl/internal/k8s"
)

const testNamespace = "qwex-demo"

func TestMakeDevPodName(t *testing.T) {
	expected := "qwex-demo-dev-pod"
	actual := makeDevelopmentPodName(testNamespace)
	if actual != expected {
		panic("makeDevelopmentPodName did not return expected value")
	}
}

func TestCreateDevPod(t *testing.T) {
	k8sClient, err := k8s.NewK8sClient()
	if err != nil {
		t.Fatalf("Expected no error creating k8s client, got %v", err)
	}
	service := Service{
		K8s: k8sClient,
	}

	res, err := service.GetOrCreateDevelopmentPod(t.Context(), testNamespace)

	if err != nil {
		t.Fatalf("Expected no error creating dev pod, got %v", err)
	}

	t.Logf("Created/Retrieved dev pod: %s", res.Name)

	if res.Name != makeDevelopmentPodName(testNamespace) {
		t.Fatalf("Expected pod name %s, got %s", makeDevelopmentPodName(testNamespace), res.Name)
	}

	if res.Status.Phase != "Running" {
		t.Fatalf("CreateDevelopmentPod should wait until pod is running, got status %s", res.Status.Phase)
	}
}

func TestDestroyDevPod(t *testing.T) {
	k8sClient, err := k8s.NewK8sClient()
	if err != nil {
		t.Fatalf("Expected no error creating k8s client, got %v", err)
	}
	service := Service{
		K8s: k8sClient,
	}

	err = service.DestroyDevelopmentPod(t.Context(), testNamespace)

	if err != nil {
		t.Fatalf("Expected no error destroying dev pod, got %v", err)
	}

	t.Logf("Destroyed dev pod in namespace: %s", testNamespace)
}
