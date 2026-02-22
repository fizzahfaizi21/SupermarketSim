class UserSession:
    def __init__(self):
        self.curr_user = None
    
    # to store active user
    def set_curr_user(self, user):
        self.curr_user=user

    # to end session
    def logout(self):
        if self.curr_user is None:
            print(f"No user is currently logged in.")
        else:
            print(f"{self.curr_user} has been logged out.")
            self.curr_user=None

    # to check who is logged in
    def get_curr_user(self):
        return self.curr_user