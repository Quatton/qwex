package pods

import "fmt"

const (
	DeploymentLabel = "qwex.dev/deployment"

	WorkspaceVolumeName    = "workspace"
	WorkspaceMountPath     = "/workspace"
	WorkspacePVCNameSuffix = "workspace-pvc"

	InitContainerName = "init-synccontainer"

	DevelopmentDeploymentSuffix = "dev"
	DevContainerName            = "devcontainer"

	// TODO: Make this configurable
	DevelopmentDemoImage = "ghcr.io/astral-sh/uv:0.9.13-python3.12-bookworm"

	SyncContainerName = "synccontainer"
	SyncImage         = "alpine/git:latest"
)

func makeDevelopmentName(namespace string) string {
	return fmt.Sprintf("%s-%s", namespace, DevelopmentDeploymentSuffix)
}

func makePVCName(namespace string) string {
	return fmt.Sprintf("%s-%s", namespace, WorkspacePVCNameSuffix)
}
