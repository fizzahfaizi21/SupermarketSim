import pygame
import pygame_widgets
from pygame_widgets.button import Button
from pygame_widgets.textbox import TextBox
#for connecting to user to db database
from models import register as db_registeration

pygame.init()
username = '' 
password = ''
register = True;


minimumUserLength = 5
minimumPassLength = 5


def drawText(text,fontSize, text_color,xPos,yPos):
    font = pygame.font.SysFont(None,fontSize)
    txt = font.render(text,True,text_color)
    screen.blit(txt,(xPos,yPos))

def submitInfo(user,pwd):
    print(user)
    print(pwd)
    if len(minimumUserLength) > 5 and len(minimumPassLength) > 5:
        if register:
            #add to database 
            print("username is: " + user + " Password is: " + pwd)
            db_registeration.register_user(user,pwd)
            hideLogin()
        elif register == False:
            #Login
            db_registeration.login_user(user,pwd)
            hideLogin()


# determine if either user is registering or logging in by using register boolean.
def registerActive(regBtn,logBtn):
    global register
    register = True
    print(logBtn.inactiveColour)

def loginActive(regBtn,logBtn):
    global register
    register = False 
    print(logBtn.inactiveColour)

    
#Creates window
screen = pygame.display.set_mode((720, 720))



#Creates button. onClick is the function that occurs when the button is pressed
username_txtBox = TextBox(screen, 100, 70, 150, 30, fontSize=20, borderColour=(0, 0, 0), borderThickness = 1, textColour=(0, 0, 0) ,
)
password_txtBox = TextBox(screen, 100, 100, 150, 30, fontSize=20, borderColour=(0, 0, 0), borderThickness = 1, textColour=(0, 0, 0) ,
 )
submitBtn = Button(screen, 10, 150, 100, 50,text = "submit", FontSize = 24, onClick=lambda: submitInfo(username_txtBox.getText(),password_txtBox.getText()))

registerBtn = Button(screen, 0, 0, 90, 50,text = "Register", FontSize = 24, onClick=lambda: registerActive(registerBtn,LoginBtn))
LoginBtn = Button(screen, 100, 0, 90, 50,text = "Login", FontSize = 24, onClick=lambda: loginActive(registerBtn,LoginBtn))


#hides the username, password, and submit buttons once done with them.
def hideLogin():
    username_txtBox.hide()
    password_txtBox.hide()
    submitBtn.hide()
    registerBtn.hide()
    LoginBtn.hide()
#shows the username, password, and submit buttons when you need them again such as with logging out.
def showLogin():
    username_txtBox.show()
    password_txtBox.show()
    submitBtn.show()
    registerBtn.hide()
    LoginBtn.hide()

def main():
    run = True
    while run:

        # darkening button of currently selected mode (login or register). lighten inactive mode.
        if register:
            registerBtn.inactiveColour = (100,100,100)
            LoginBtn.inactiveColour = (200,200,200)
            
        else:
            LoginBtn.inactiveColour = (100,100,100)
            registerBtn.inactiveColour = (200,200,200)

        #quit using top left quit button
        events = pygame.event.get()
        for event in events:
            
            if event.type == pygame.QUIT:
                pygame.quit()
                run = False
                quit()

        screen.fill((255, 255, 255))
        #changes top text to show player whether they are logging in or registering
        if register:
            registerorLoginTxt = drawText("=== Register ===", 24,(0,0,0),10,50)
        else:
            registerorLoginTxt = drawText("=== Login ===", 24,(0,0,0),10,50)
        usernameText = drawText("Username: ", 24,(0,0,0),10, 70)
        passwordText = drawText("Password: ", 24,(0,0,0),10, 100)
    
        pygame_widgets.update(events)
        pygame.display.update()
main()