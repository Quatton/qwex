package routes

var (
	BearerAuth = []map[string][]string{
		{"bearer": {}},
	}
)

type Tag string

const (
	TagController Tag = "controller"
	TagHealth     Tag = "health"
	TagIam        Tag = "iam"
	TagUsers      Tag = "users"
)

func (t Tag) String() string { return string(t) }

func AllTags() []string {
	return []string{
		TagController.String(),
		TagHealth.String(),
		TagIam.String(),
		TagUsers.String(),
	}
}
