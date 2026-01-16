package connect

import (
	"os"
	"os/exec"
	"path"
	"strings"

	"k8s.io/client-go/kubernetes"
	"k8s.io/client-go/rest"
)

type Service struct {
	Client        kubernetes.Interface
	Config        *rest.Config
	Namespace     string
	PodName       string
	ContainerName string
	LocalRepoPath string
}

func GetLocalRepoPath(cfgFile string) string {
	startDir, err := os.Getwd()
	if err != nil {
		startDir = "."
	}
	if cfgFile != "" {
		startDir = path.Dir(cfgFile)
	}

	gitRoot, err := exec.Command("git", "-C", startDir, "rev-parse", "--show-toplevel").Output()

	if err != nil {
		return startDir
	}

	return strings.TrimSpace(string(gitRoot))
}

func NewService(
	k8sClient kubernetes.Interface,
	config *rest.Config,
	namespace string,
	podName string,
	containerName string,
	localRepoPath string,
) *Service {
	return &Service{
		Client:        k8sClient,
		Config:        config,
		Namespace:     namespace,
		PodName:       podName,
		ContainerName: containerName,
		LocalRepoPath: localRepoPath,
	}
}
