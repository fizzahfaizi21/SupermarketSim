import pygame
import pygame_widgets
from pygame_widgets.button import Button
from pygame_widgets.textbox import TextBox

pygame.init()
username = '' 
password = ''

def drawText(text,fontSize, text_color,xPos,yPos):
    font = pygame.font.SysFont(None,fontSize)
    txt = font.render(text,True,text_color)
    screen.blit(txt,(xPos,yPos))

def submitInfo(user,pwd):
    print(user)
    print(pwd)
    if len(user) > 0 and len(pwd) > 0:
        print("username is: " + user + " Password is: " + pwd);
#Creates window
screen = pygame.display.set_mode((720, 720))

#Creates button. onClick is the function that occurs when the button is pressed
username_Text = TextBox(screen, 100, 70, 150, 30, fontSize=12, borderColour=(0, 0, 0), borderThickness = 1, textColour=(0, 0, 0) ,
)
password_Text = TextBox(screen, 100, 100, 150, 30, fontSize=12, borderColour=(0, 0, 0), borderThickness = 1, textColour=(0, 0, 0) ,
 )
submitBtn = Button(screen, 10, 150, 100, 50,text = "submit", FontSize = 24, onClick=lambda: submitInfo(username_Text.getText(),password_Text.getText()))


run = True
while run:
    events = pygame.event.get()
    for event in events:
        
        if event.type == pygame.QUIT:
            pygame.quit()
            run = False
            quit()
    #print(username_Text.getText())
    screen.fill((255, 255, 255))
    register = drawText("=== Register ===", 24,(0,0,0),10,50)
    drawText("Username: ", 24,(0,0,0),10, 70)
    drawText("Password: ", 24,(0,0,0),10, 100)


    # Now
    pygame_widgets.update(events)

    # Instead of
    pygame.display.update()