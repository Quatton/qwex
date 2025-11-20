package qrunner

// ContainerConfig represents configuration shared between container-based runners
// (Docker, K8s, etc.) for launching qwex in a containerized environment
type ContainerConfig struct {
	// Image is the container image that contains the qwex binary
	Image string

	// Resources defines CPU and memory constraints
	Resources ResourceRequirements

	// Mounts defines volume mounts for the container
	Mounts []Mount

	// NetworkMode defines the network configuration (e.g., "host", "bridge")
	NetworkMode string
}

// ResourceRequirements defines CPU and memory constraints in a format
// that can be translated to Docker or Kubernetes resource specifications
type ResourceRequirements struct {
	// CPU request in Kubernetes format (e.g., "100m", "1", "2")
	CPURequest string

	// Memory request in Kubernetes format (e.g., "128Mi", "1Gi")
	MemoryRequest string

	// CPU limit in Kubernetes format
	CPULimit string

	// Memory limit in Kubernetes format
	MemoryLimit string
}

// Mount represents a volume mount for containers
type Mount struct {
	// Type is the mount type: "bind" for host paths, "volume" for named volumes
	Type string

	// Source is the source path (host) or volume name
	Source string

	// Destination is the target path inside the container
	Destination string

	// ReadOnly indicates if the mount should be read-only
	ReadOnly bool
}

// WrapCommandForLocal wraps a command to be executed via "qwex run --local"
// This allows container-based runners to delegate actual execution to LocalRunner
// inside the container.
//
// Example:
//   Input:  command="echo", args=["hello", "world"]
//   Output: command="qwex", args=["run", "--local", "echo", "hello", "world"]
func WrapCommandForLocal(command string, args []string) (string, []string) {
	wrappedArgs := []string{"run", "--local", command}
	wrappedArgs = append(wrappedArgs, args...)
	return "qwex", wrappedArgs
}

// DefaultContainerConfig returns sensible defaults for container configuration
func DefaultContainerConfig() ContainerConfig {
	return ContainerConfig{
		Image: "qwex:latest", // TODO: make this configurable
		Resources: ResourceRequirements{
			CPURequest:    "100m",
			MemoryRequest: "128Mi",
			CPULimit:      "1",
			MemoryLimit:   "512Mi",
		},
		NetworkMode: "bridge",
	}
}
