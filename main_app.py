# =================================================================================================
# Setup ===========================================================================================
# =================================================================================================

# Import
import flask
import flask_socketio
import datetime
import json

# Setup constants
with open ("config.json") as config_file:
    config_dict = json.load(config_file)
    SECRET_KEY = config_dict["secret_key"]
    LOG_LOCATION = config_dict["log_location"]
    UTC_TIMEZONE_OFFSET = config_dict["utc-timezone-offset"]
    IP_ADDRESS = config_dict["ip_address"]
    PORT = config_dict["port"]
    DEFAULT_WRONG_CHAR = config_dict["default_wrong_char"]

# Setup website
main_app = flask.Flask(__name__, template_folder = "template")
main_app.config["SECRET_KEY"] = SECRET_KEY
socket_io = flask_socketio.SocketIO(main_app)

# =================================================================================================
# Classes =========================================================================================
# =================================================================================================

# Hangman class
class Hangman:
    # Initialize
    def __init__(self):
        self.setup_variables()

    # Set up variables
    def setup_variables(self):
        self.users_connected:int = 0
        self.messages_sent:int = 0
        self.guesses_left:int = 6
        self.started:bool = False
        self.executioner_id:str = ""
        self.guesser_id:str = ""
        self.game_word:str = ""
        self.censored_game_word:str = ""
        self.guessed_letters:set = set()
        self.users_readied_up:set = set()
        self.user_database:dict = {}        # ID: Username
        self.user_points_database:dict = {} # Username: Points

    # Reset variables
    def reset_variables(self):
        self.guesses_left = 6
        self.guessed_letters.clear()
        self.users_readied_up.clear()
        self.game_word = ""

    # Update points
    def update_points(self): 
        socket_io.emit("points_update", data = self.user_points_database)
        log(text_to_log = f"Updating points!| Point database: {self.user_points_database} | {get_current_time()}")

    # Guesser won game
    def guesser_won(self):
        socket_io.emit("game_over_guesser_won", data = {"word": hangman.game_word}, broadcast = True)
        log(text_to_log = f"The guesser won! | {get_current_time()}")
        self.user_points_database[self.user_database[self.guesser_id]] += 1
        self.update_points()
    
    # Executioner won game
    def executioner_won(self): 
        socket_io.emit("game_over_out_of_guesses", data = {"word": self.game_word}, broadcast = True)
        log(text_to_log = f"The guesser ran out of guesses! | {get_current_time()}")
        self.user_points_database[self.user_database[self.executioner_id]] += 1
        self.update_points()    

    # Start game
    def start_game(self, executioner_id:str, guesser_id:str):
        self.update_points()
        self.reset_variables()

        self.started = True
        self.executioner_id = executioner_id
        self.guesser_id = guesser_id

        flask_socketio.emit("recieve_role", {"role": "executioner"}, room = self.executioner_id)
        flask_socketio.emit("recieve_role", {"role": "guesser"}, room = self.guesser_id)
        send_message(f"Game is starting! The guesser is {self.user_database[guesser_id]} and the executioner is {self.user_database[self.executioner_id]}")

        log(text_to_log = f"Starting! | Database: {self.user_database} | {get_current_time()}")

    # Guessed letter
    def guessed_letter(self, data:dict):
        letter_guessed = data["letter_guessed"]

        # Check if it has already been guessed
        if letter_guessed in self.guessed_letters:
            socket_io.emit("letter_has_already_been_guessed", room = self.guesser_id)
            return

        # Append it to guessed letters list
        self.guessed_letters.add(letter_guessed)

        # Check if the letter is in the word
        if letter_guessed in self.game_word:
            correct = True

            # Set censored word to empty
            censored_word = ""

            # Iterate through each letter in the word
            for letter_word in self.game_word:
                # Iterate through every guessed letter
                for letter_guess in self.guessed_letters:

                    # Check if it is in the word
                    if letter_guess == letter_word: 
                        censored_word += letter_guess
                        break

                # Letters didn't match, so add the default.
                else: censored_word += DEFAULT_WRONG_CHAR

            self.censored_game_word = censored_word
        
            # Check if the word has been guessed (censored word is correct)
            if self.game_word == censored_word: 
                self.guesser_won()
                return

        # Letter wasn't in word
        else:
            correct = False
            self.guesses_left -= 1

            # Check if game over
            if self.guesses_left <= 0:
                self.executioner_won()

        # Give back the censored word
        socket_io.emit(
            "letter_has_been_guessed", 
            {"letter_guessed": letter_guessed, "censored_word": self.censored_game_word, "guesses_left": self.guesses_left, "correct": correct}, 
            broadcast = True
        )

        log(text_to_log = f"A letter has been guessed! | Correct: {correct} | Data: {data} | {get_current_time()}")

hangman = Hangman()

# =================================================================================================
# Misc. functions =================================================================================
# =================================================================================================

# Log
def log(text_to_log:str, file:str = LOG_LOCATION):
    print(text_to_log)
    with open (file = LOG_LOCATION, mode = "a") as log_text_file: log_text_file.write(text_to_log + "\n")

# Get current time (shifted to timezone)
def get_current_time():
    return (datetime.datetime.utcnow() + datetime.timedelta(hours = UTC_TIMEZONE_OFFSET)).strftime("%m/%d/%Y at %H:%M:%S")

# Escape HTML scripting
def escape_html(text:str):
    text = text.replace(">", "&gt;")
    return text.replace("<", "&lt;")

# Check username
def check_username(username:str):
    # Blank username
    if len(username) == 0: flask.flash("Invalid username: too short.")
    # Full game
    elif hangman.users_connected >= 2: flask.flash("This game is full. Sorry!")
    # Regex check
    elif not username.isalnum(): flask.flash("Your username must be letters and numbers only.")    

    # Send to hangman game with username
    else:
        try:
            # Make sure username is not already in database
            for username_db in hangman.user_database.values():
                if username_db.lower() == username.lower():
                    flask.flash(f"Username \"{username_db}\" is already in use.")
                    break
            else: return True

        # Either a GET request username not submitted
        except Exception: pass
    
    # If haven't returned, then it didn't pass
    return False

# =================================================================================================
# Hangman functions ===============================================================================
# =================================================================================================

# Connect / Disconnect 

# User connection handler
@socket_io.on("user_connection")
def user_connect_handler(data:dict):
    # If the username check failed, close the connection. 
    # This most likely happens when the back button is pressed.
    if not check_username(username = data["username"]): 
        # Before we disconnect them, try to send them back to the main page
        socket_io.emit("redirect", {"new_url": "/"}, room = flask.request.sid)

    # Update variables
    hangman.user_database[flask.request.sid] = data["username"]
    hangman.users_connected = len(hangman.user_database)
    hangman.user_points_database[data["username"]] = 0
    hangman.update_points()

    send_message(message = f"{data['username']} has joined the game! There are now {hangman.users_connected}/2 users in the game.")

    # If there are more than two people, get the guesser and executioner.
    all_user_ids = list(hangman.user_database.keys())
    if len(all_user_ids) >= 2: hangman.start_game(executioner_id = all_user_ids[0], guesser_id = all_user_ids[1])

    log(text_to_log = f"{flask.request.sid}: {data['username']} joined | Database: {hangman.user_database} | {get_current_time()}")

# User disconnection handler
def user_disconnection_handler(user_id:str, username:str):
    # Update variables
    del hangman.user_database[user_id]
    hangman.users_connected = len(hangman.user_database)
    del hangman.user_points_database[username]
    hangman.update_points()

    send_message(message = f"{username} has left the game! There are now {hangman.users_connected}/2 users in this game.")

    # If there is a disconnect while the game has started, end the game.
    if hangman.started:
        socket_io.emit("end_game_disconnect", broadcast = True)
        # Reset variables
        hangman.reset_variables()

    log(text_to_log = f"{user_id}: {username} left | Database: {hangman.user_database} | {get_current_time()}")

@socket_io.on("disconnect")
def disconnection():
    # Get username
    try: username = hangman.user_database[flask.request.sid]
    # Username wasn't in database, so just exit
    except KeyError: return

    # Call disconnection handler
    user_disconnection_handler(user_id = flask.request.sid, username = username)

@socket_io.on("client_disconnect") # Disconnect is reserved, so we call this when the client wants to disconnect.
def client_disconnection():
    # Call disconnection handler
    try: user_disconnection_handler(user_id = flask.request.sid, username = hangman.user_database[flask.request.sid])
    # Not in database, just pass
    except KeyError: pass

    # Redirect user
    flask_socketio.emit("redirect", {"new_url": "/"}, room = flask.request.sid)

# Chat

# Send message
def send_message(message): flask_socketio.send(message, broadcast = True)

# Send message handler
@socket_io.on("send_message")
def send_message_handler(data:dict):
    hangman.messages_sent += 1
    message = escape_html(text = data["message"])
    send_message(message = f"[#{str(hangman.messages_sent).zfill(4)}] {hangman.user_database[flask.request.sid]}: {message}")

    log(text_to_log = f"{flask.request.sid}: {hangman.user_database[flask.request.sid]} sent message with data: \"{data}\" | {get_current_time()}")

# Message handler
@socket_io.on("message")
def message_handler(message:str):
    print(f"Message recieved at {datetime.datetime.utcnow()} (GMT): \"{message}\"")
    send_message(message = message)

    log(text_to_log = f"Sending message to all: {message} | {get_current_time()}")

# Game

# Word for guesser
@socket_io.on("word_for_guesser")
def word_for_guesser(data:dict):
    # Put the word into the word
    hangman.game_word = data["word"]
    hangman.censored_game_word = data["censored_word"]
    flask_socketio.emit("get_word", data, room = hangman.guesser_id)

    log(text_to_log = f"Sending word to guesser (id {hangman.guesser_id}) | Data: {data} | Database: {hangman.user_database} | {get_current_time()}")

# Guesser guessed a letter
@socket_io.on("guessed_letter")
def guessed_letter(data:dict): hangman.guessed_letter(data = data)

# Readied up
@socket_io.on("ready_up")
def ready_up():
    # Check if the user already readied up
    if hangman.user_database[flask.request.sid] in hangman.users_readied_up: return
    
    # User has not already readied up, add them to the set
    hangman.users_readied_up.add(hangman.user_database[flask.request.sid])

    # Check if both players have readied up
    if len(hangman.users_readied_up) >= 2:
        # Start game with switched roles
        hangman.start_game(executioner_id = hangman.guesser_id, guesser_id = hangman.executioner_id)

    # Hasn't started game yet, so update the button
    else: flask_socketio.emit("user_readied_up", broadcast = True)

    log(text_to_log = f"User {hangman.user_database[flask.request.sid]} has readied up! | {get_current_time()}")

# =================================================================================================
# Website navigation ==============================================================================
# =================================================================================================

# Errors

# 404 - Page not found
@main_app.errorhandler(404)
def page_not_found(error):
    return flask.render_template("page_not_found.html"), 404

# 500 - Internal server error
@main_app.errorhandler(500)
def internal_server_error(error):
    return flask.render_template("internal_server_error.html"), 500

# Pages

# Join game
@main_app.route("/")
def join_game(): return flask.render_template("join.html")

# Hangman game
@main_app.route("/hangman", methods = ["POST", "GET"])
def hangman_web_page():
    try: username = flask.request.form["username_input"]
    # Username was not entered (either that or GET request)
    except KeyError: return flask.redirect("/")
    
    # Check username
    if not check_username(username = username): return flask.redirect("/")

    # Didn't return means the username was good, send to the hangman page.
    return flask.render_template("hangman.html", username = username, ip_address = IP_ADDRESS, port = PORT, default_wrong_char = DEFAULT_WRONG_CHAR)

# Run
if __name__ == "__main__":
    socket_io.run(main_app, host = "127.0.0.1", port = 5000, debug = True) # Local, debug
    # socket_io.run(main_app, host = "127.0.0.1", port = 5000, debug = False) # Local, no debug
    # socket_io.run(main_app, debug = False, host = "0.0.0.0", port = PORT) # Production

else: print("You must run this by itself.")