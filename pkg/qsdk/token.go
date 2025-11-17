package qsdk

import (
	"strings"

	"github.com/zalando/go-keyring"
)

const keyringService = "qwex"

// normalizeKey converts a baseURL into a stable key name for keyring storage.
// It currently trims trailing slashes and lowercases the host portion to avoid
// accidental duplicates like https://example.com/ and https://example.com.
func normalizeKey(baseURL string) string {
	s := strings.TrimSpace(baseURL)
	s = strings.TrimRight(s, "/")
	s = strings.ToLower(s)
	return s
}

// SaveToken stores the token in the OS keyring under the normalized baseURL
// key. Note: this is intentionally simple (baseURL-only) so it can be used
// immediately with existing config; future versions may use per-account keys.
func SaveToken(baseURL string, token string) error {
	key := normalizeKey(baseURL)
	return keyring.Set(keyringService, key, token)
}

// LoadToken retrieves the token stored for the given baseURL. If no token is
// found the underlying keyring error is returned. Callers may want to
// distinguish 'not found' (platform-dependent) versus other keyring errors.
func LoadToken(baseURL string) (string, error) {
	key := normalizeKey(baseURL)
	return keyring.Get(keyringService, key)
}

// DeleteToken removes the token entry for the given baseURL from the OS
// keyring. It is a convenience for logout flows.
func DeleteToken(baseURL string) error {
	key := normalizeKey(baseURL)
	return keyring.Delete(keyringService, key)
}
