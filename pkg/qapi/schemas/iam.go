package schemas

type User struct {
	ID    string `json:"id" doc:"Unique identifier for the principal"`
	Login string `json:"login" doc:"Login name of the principal"`
	Name  string `json:"name" doc:"Full name of the principal"`
	Email string `json:"email" doc:"Email address of the principal"`
}

type MeResponse struct {
	Body struct {
		User User `json:"user"`
	}
}
