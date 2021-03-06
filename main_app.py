# =================================================================================================
# Setup ===========================================================================================
# =================================================================================================

# Import
import flask
import flask_socketio
import datetime
import json
import traceback

# Setup constants
with open ("config.json") as config_file:
    config_dict = json.load(config_file)
    SECRET_KEY = config_dict["secret_key"]
    LOG_LOCATION = config_dict["log_location"]
    UTC_TIMEZONE_OFFSET = config_dict["utc_timezone_offset"]
    IP_ADDRESS = config_dict["ip_address"]
    PORT = config_dict["port"]
    DEFAULT_WRONG_CHAR = config_dict["default_wrong_char"]
    ROOMS = config_dict["rooms"]

# Unimport JSON module as it is no longer required
del json

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
    def __init__(self, namespace:str): 
        self.setup_variables()
        self.namespace = namespace

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
    def update_points(self): socket_io.emit("points_update", data = self.user_points_database, broadcast = True, namespace = self.namespace)

    # Guesser won game
    def guesser_won(self):
        socket_io.emit("game_over_guesser_won", data = {"word": self.game_word}, broadcast = True, namespace = self.namespace)
        self.user_points_database[self.user_database[self.guesser_id]] += 1
        self.update_points()

        log(text_to_log = f"The guesser won! | {get_current_time()}")
    
    # Executioner won game
    def executioner_won(self): 
        socket_io.emit("game_over_out_of_guesses", data = {"word": self.game_word}, broadcast = True, namespace = self.namespace)
        self.user_points_database[self.user_database[self.executioner_id]] += 1
        self.update_points()    

        log(text_to_log = f"The guesser ran out of guesses! | {get_current_time()}")

    # Start game
    def start_game(self, executioner_id:str, guesser_id:str):
        self.update_points()
        self.reset_variables()

        self.started = True
        self.executioner_id = executioner_id
        self.guesser_id = guesser_id

        flask_socketio.emit("recieve_role", {"role": "executioner"}, room = self.executioner_id, namespace = self.namespace)
        flask_socketio.emit("recieve_role", {"role": "guesser"}, room = self.guesser_id, namespace = self.namespace)
        flask_socketio.send(f"Game is starting! The guesser is {self.user_database[guesser_id]} and the executioner is {self.user_database[self.executioner_id]}", namespace = self.namespace)

        log(text_to_log = f"Starting! | Database: {self.user_database} | {get_current_time()}")

    # Guessed letter
    def guessed_letter(self, data:dict):
        letter_guessed = data["letter_guessed"]

        # Check if it has already been guessed
        if letter_guessed in self.guessed_letters:
            socket_io.emit("letter_has_already_been_guessed", room = self.guesser_id, namespace = namespace)
            return

        self.guessed_letters.add(letter_guessed)

        # Check if the letter is in the word
        if letter_guessed in self.game_word:
            correct = True
            censored_word = ""

            for letter_word in self.game_word:
                for letter_guess in self.guessed_letters:
                    # Check if it is in the word
                    if letter_guess == letter_word: 
                        censored_word += letter_guess
                        break

                # Letters guessed didn't match
                else: censored_word += DEFAULT_WRONG_CHAR
            self.censored_game_word = censored_word
        
            # Check if word guessed
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
                return

        socket_io.emit(
            "letter_has_been_guessed", 
            {"letter_guessed": letter_guessed, "censored_word": self.censored_game_word, "guesses_left": self.guesses_left, "correct": correct}, 
            broadcast = True,
            namespace = self.namespace
        )

        log(text_to_log = f"A letter has been guessed! | Correct: {correct} | Data: {data} | {get_current_time()}")

# All hangman rooms (shared between all hangman rooms)
class AllHangmanRooms: room_dicts:dict = {}
all_hangman_rooms = AllHangmanRooms() # Shared instance between all hangman rooms

# Hangman room class
class HangmanRoom(flask_socketio.Namespace):
    # Initialize
    def __init__(self, namespace:str, all_hangman_rooms:object): 
        self.hangman = Hangman(namespace = namespace)
        self.namespace = namespace
        self.all_hangman_rooms = all_hangman_rooms
        self.all_hangman_rooms.room_dicts[(self.namespace.lstrip("/"))] = {"user_database": set()} # Setup entry in all hangman rooms

    # Connect / Disconnect 

    # User connection handler
    def on_user_connection(self, data:dict):
        # If the username check failed, send them back to join page.
        if not check_username(username = data["username"], namespace = self.namespace.lstrip("/")): 
            socket_io.emit("redirect", {"new_url": "/"}, room = flask.request.sid, namespace = self.namespace)
            return

        # Update variables
        self.hangman.user_database[flask.request.sid] = data["username"]
        self.hangman.users_connected = len(self.hangman.user_database)
        self.hangman.user_points_database[data["username"]] = 0
        self.hangman.update_points()
        self.all_hangman_rooms.room_dicts[(self.namespace.lstrip("/"))]["user_database"].add(data["username"])

        self.send_message(message = f"{data['username']} has joined the game! There are now {self.hangman.users_connected}/2 users in the game.")

        all_user_ids = list(self.hangman.user_database.keys())
        if len(all_user_ids) >= 2: self.hangman.start_game(executioner_id = all_user_ids[0], guesser_id = all_user_ids[1])

        log(text_to_log = f"{flask.request.sid}: {data['username']} joined | Database: {self.hangman.user_database} | {get_current_time()}")

    # User disconnection handler
    def user_disconnection_handler(self, user_id:str, username:str):
        # Update variables
        del self.hangman.user_database[user_id]
        self.hangman.users_connected = len(self.hangman.user_database)
        del self.hangman.user_points_database[username]
        self.hangman.update_points()
        self.all_hangman_rooms.room_dicts[(self.namespace.lstrip("/"))]["user_database"].remove(username)

        self.send_message(message = f"{username} has left the game! There are now {self.hangman.users_connected}/2 users in this game.")

        # If there is a disconnect while the game has started, end the game.
        if self.hangman.started:
            socket_io.emit("end_game_disconnect", broadcast = True)
            self.hangman.reset_variables()

        log(text_to_log = f"{user_id}: {username} left | Database: {self.hangman.user_database} | {get_current_time()}")

    def on_disconnect(self):
        # Get username
        try: username = self.hangman.user_database[flask.request.sid]
        # Username wasn't in database, so just exit
        except KeyError: return

        self.user_disconnection_handler(user_id = flask.request.sid, username = username)

    def on_client_disconnect(self): # Disconnect is reserved, so we call this when the client wants to disconnect.
        try: self.user_disconnection_handler(user_id = flask.request.sid, username = self.hangman.user_database[flask.request.sid])
        # Not in database, just pass
        except KeyError: pass

        # Redirect user
        flask_socketio.emit("redirect", {"new_url": "/"}, room = flask.request.sid, namespace = self.namespace)

    # Chat

    # Send message handler
    def send_message(self, message): flask_socketio.send(message, broadcast = True)

    # Send message 
    def on_send_message(self, data:dict):
        self.hangman.messages_sent += 1
        message = escape_html(text = data["message"])
        self.send_message(message = f"[#{str(self.hangman.messages_sent).zfill(4)}] {self.hangman.user_database[flask.request.sid]}: {message}")

        log(text_to_log = f"{flask.request.sid}: {self.hangman.user_database[flask.request.sid]} sent message with data: \"{data}\" | {get_current_time()}")

    # Message handler
    def message(self, message:str):
        print(f"Message recieved at {datetime.datetime.utcnow()} (GMT): \"{message}\"")
        self.send_message(message = message)

        log(text_to_log = f"Sending message to all: {message} | {get_current_time()}")

    # Game

    # Word for guesser
    def on_word_for_guesser(self, data:dict):
        word = data["word"]

        # Check if word is empty
        if len(word) == 0: flask_socketio.emit("status_change", {"status": "<h4>The word cannot be empty.</h4>"}, room = self.hangman.executioner_id)
        # Check if word is too long (25 chars)
        elif len(word) > 25: flask_socketio.emit("status_change", {"status": "<h4>The word cannot be more than 25 characters.</h4>"}, room = self.hangman.executioner_id)
        # Check if word is not a word (not made of letters)
        elif not word.isalpha(): flask_socketio.emit("status_change", {"status": "<h4>The word must be composed of only letters.</h4>"}, room = self.hangman.executioner_id)

        # Checks passed
        else:
            self.hangman.game_word = word
            self.hangman.censored_game_word = f"{DEFAULT_WRONG_CHAR}" * len(word)

            flask_socketio.emit("word_passed", {"word": word}, room = self.hangman.executioner_id)
            flask_socketio.emit("get_word", {"word": word, "censored_word": self.hangman.censored_game_word}, room = self.hangman.guesser_id)
            flask_socketio.emit("setup_censored_word", {"censored_word": self.hangman.censored_game_word}, room = self.hangman.executioner_id)

            log(text_to_log = f"Sending word to guesser (id {self.hangman.guesser_id}) | Data: {data} | Database: {self.hangman.user_database} | {get_current_time()}")

    # Guesser guessed a letter
    def on_guessed_letter(self, data:dict):
        letter_guessed = data["letter_guessed"]

        # Check if letter is empty
        if len(letter_guessed) == 0: flask_socketio.emit("status_change", {"status": "<h4>The letter cannot be empty.</h4>"}, room = self.hangman.guesser_id)

        # Check if letter is longer than a letter
        elif len(letter_guessed) > 1: flask_socketio.emit("status_change", {"status": "<h4>The letter cannot be more than one letter.</h4>"}, room = self.hangman.guesser_id)
        
        # Check if letter is not a letter
        elif not letter_guessed.isalpha(): flask_socketio.emit("status_change", {"status": "<h4>The letter must be an alphabetical letter.</h4>"}, room = self.hangman.guesser_id)

        # Checks passed
        else: self.hangman.guessed_letter(data = data)

    # Ready up
    def on_ready_up(self):
        # Check if the user already readied up
        if self.hangman.user_database[flask.request.sid] in self.hangman.users_readied_up: return
        
        # User has not already readied up, add them to the set
        self.hangman.users_readied_up.add(self.hangman.user_database[flask.request.sid])

        # Check if both players have readied up
        if len(self.hangman.users_readied_up) >= 2:
            # Start game with switched roles
            self.hangman.start_game(executioner_id = self.hangman.guesser_id, guesser_id = self.hangman.executioner_id)

        # Hasn't started game yet, so update the button
        else: flask_socketio.emit("user_readied_up", broadcast = True)

        log(text_to_log = f"User {self.hangman.user_database[flask.request.sid]} has readied up! | {get_current_time()}")

# Setup rooms
for room in ROOMS: socket_io.on_namespace(HangmanRoom(f"/{room}", all_hangman_rooms = all_hangman_rooms))

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
def escape_html(text:str): return text.replace(">", "&gt;").replace("<", "&lt;")

# Check username
def check_username(username:str, namespace:str):
    user_database = all_hangman_rooms.room_dicts[namespace]["user_database"]

    # Check if username is blank
    if len(username) == 0: flask.flash("Invalid username: too short.")
    # Check if room is full
    elif len(user_database) >= 2: flask.flash("This room is full. Sorry!")
    # Check if the username is a valid username
    elif not username.isidentifier(): flask.flash("Your username must only contain alphanumeric characters and underscores, and may not start with a number.")    

    # Send to hangman game with username
    else:
        try:
            # Make sure username is not already in database
            for username_db in user_database:
                if username_db.lower() == username.lower():
                    flask.flash(f"Username \"{username_db}\" is already in use.")
                    break
                
            else: return True

        # Either a GET request username not submitted
        except Exception as error: flask.flash(f"An error occured! The error was: \"{error}\"")
    
    # If haven't returned, then it didn't pass
    return False

# =================================================================================================
# Website navigation ==============================================================================
# =================================================================================================

# Errors

# 404 - Page not found
@main_app.errorhandler(404)
def page_not_found(error):
    return flask.render_template("page_not_found.html", traceback = traceback.format_exc()), 404

# 500 - Internal server error
@main_app.errorhandler(500)
def internal_server_error(error):
    return flask.render_template("internal_server_error.html", traceback = traceback.format_exc()), 500

# Pages

# Join game
@main_app.route("/")
def join_game(): return flask.render_template("join.html", rooms = ROOMS)

# Hangman game
@main_app.route("/hangman", methods = ["POST", "GET"])
def hangman_web_page():
    try: 
        username = flask.request.form["username_input"]
        room = flask.request.form["room_selection"]
    # Username or name was not entered (either that or GET request)
    except KeyError: return flask.redirect("/")
    
    # Check username
    if not check_username(username = username, namespace = room): return flask.redirect("/")

    # Didn't return means the username was good, send to the hangman page.
    return flask.render_template(
        "hangman.html",
        username = username, 
        ip_address = IP_ADDRESS, 
        port = PORT, 
        room_name = room
    )

# Run
if __name__ == "__main__":
    socket_io.run(main_app, host = "127.0.0.1", port = 5000, debug = True) # Local, debug
    # socket_io.run(main_app, host = "127.0.0.1", port = 5000, debug = False) # Local, no debug
    # socket_io.run(main_app, debug = False, host = "0.0.0.0", port = PORT) # Production

else: print("You must run this by itself.")