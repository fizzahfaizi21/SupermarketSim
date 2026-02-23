class UserSession:
    def __init__(self):
        self.curr_user = None

    def set_curr_user(self, user):
        self.curr_user = user

    def logout(self):
        if self.curr_user is None:
            print("No user is currently logged in.")
        else:
            print(f"{self.curr_user[1]} has been logged out.")
            self.curr_user = None

    def get_curr_user(self):
        return self.curr_user
    
current_user = None

def login(user):
    global current_user
    current_user = user

def logout():
    global current_user
    current_user = None

def get_current_user():
    return current_user

from systems.session import logout

def logout_menu():
    logout()
    print("You have been logged out.")

from systems.session import get_current_user

def is_admin():
    user = get_current_user()
    return user and user[2] == "admin"
def admin_panel():
    if not is_admin():
        print("Access denied.")
        return
    print("Welcome to Admin Panel")