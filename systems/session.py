current_user = None

def login(user):
    global current_user
    current_user = user

def logout():
    global current_user
    if current_user:
        print(f"{current_user[1]} has been logged out.")
    current_user = None

def get_current_user():
    return current_user

def is_admin():
    return current_user is not None and current_user[2] == "admin"