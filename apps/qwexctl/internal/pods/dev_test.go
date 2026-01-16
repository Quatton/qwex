package pods

import (
	"testing"

	"github.com/Quatton/qwex/apps/qwexctl/internal/k8s"
	v1 "k8s.io/api/apps/v1"
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
	k8sClient, err := k8s.NewK8sClient()
	if err != nil {
		t.Fatalf("Expected no error creating k8s client, got %v", err)
	}
	service := Service{
		K8s: k8sClient,
	}

	res, err := service.GetOrCreateDevelopmentDeployment(t.Context(), testNamespace)

	if err != nil {
		t.Fatalf("Expected no error creating dev pod, got %v", err)
	}

	t.Logf("Created/Retrieved dev pod: %s", res.Name)

	if res.Name != makeDevelopmentName(testNamespace) {
		t.Fatalf("Expected pod name %s, got %s", makeDevelopmentName(testNamespace), res.Name)
	}

	if res.Status.Conditions[len(res.Status.Conditions)-1].Type != v1.DeploymentAvailable {
		t.Fatalf("Expected deployment to be available, got %s", res.Status.Conditions[len(res.Status.Conditions)-1].Type)
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

	err = service.DestroyDevelopment(t.Context(), testNamespace)

	if err != nil {
		t.Fatalf("Expected no error destroying dev pod, got %v", err)
	}

	t.Logf("Destroyed dev pod in namespace: %s", testNamespace)
}
