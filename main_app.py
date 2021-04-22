# Setup ===========================================================================================
# Import
import flask
import flask_socketio
import datetime
import json

# Counter class
class Counter:
    def __init__(self, initial_value:int = 0): self.count = initial_value
    def change(self, by:int = 1): self.count += by
    def get(self) -> int: return self.count

# Global variable class
class GlobalVariable:
    def __init__(self, initial_value = None): self.var = initial_value

# Setup
with open ("config.json") as config_file:
    config_dict = json.load(config_file)
    SECRET_KEY = config_dict["secret_key"]
    LOG_LOCATION = config_dict["log_location"]
    UTC_TIMEZONE_OFFSET = config_dict["utc-timezone-offset"]
    IP_ADDRESS = config_dict["ip_address"]
    PORT = config_dict["port"]

main_app = flask.Flask(__name__, template_folder = "template")
main_app.config["SECRET_KEY"] = SECRET_KEY
socket_io = flask_socketio.SocketIO(main_app)

# Setup globals
users_connected = Counter(initial_value = 0)
messages_sent = Counter(initial_value = 0)
guesses_left = Counter(initial_value = 6)
started_global = GlobalVariable(initial_value = False)
executioner_id_global = GlobalVariable()
guesser_id_global = GlobalVariable()
guessed_letters_global = GlobalVariable(initial_value = [])
game_word_global = GlobalVariable()
censored_game_word_global = GlobalVariable()
user_database = {}

# Misc. functions =================================================================================

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
    elif len(user_database) > 2: flask.flash("This game is full. Sorry!")    

    # Send to hangman game with username
    else:    
        try:
            # Make sure username is not already in database
            for username_db in user_database.values():
                if username_db.lower() == username.lower():
                    flask.flash(f"Username \"{username_db}\" is already in use.")
                    break
            else: return True

        # Either a GET request username not submitted
        except Exception: pass
    
    # If haven't returned, then it didn't pass
    return False

# Reset variables
def reset_variables():
    started_global.var = False
    executioner_id_global.var = None
    guesser_id_global.var = None
    users_connected.count = 0
    messages_sent.count = 0
    guesses_left.count = 6
    game_word_global.var = None
    guessed_letters_global.var = []

# Hangman functions ===============================================================================

# Send message
def send_message(message): flask_socketio.send(message, broadcast = True)

# Start game
def start_game(executioner_id:str, guesser_id:str):
    started_global.var = True

    # Put the host and player id into a namespace variable
    executioner_id_global.var = executioner_id
    guesser_id_global.var = guesser_id

    flask_socketio.emit("recieve_role", {"role": "executioner"}, room = executioner_id)
    flask_socketio.emit("recieve_role", {"role": "guesser"}, room = guesser_id)

    log(text_to_log = f"Starting! | Database: {user_database} | {get_current_time()}")
    send_message(f"Game is starting! The guesser is {user_database[guesser_id]} and the executioner is {user_database[executioner_id]}")

# Word for guesser
@socket_io.on("word_for_guesser")
def word_for_guesser(data:dict):
    # Put the word into the global word var
    game_word_global.var = data["word"]
    censored_game_word_global.var = data["censored_word"]

    log(text_to_log = f"Sending word to guesser (id {guesser_id_global.var}) | Data: {data} | Database: {user_database} | {get_current_time()}")
    flask_socketio.emit("get_word", data, room = guesser_id_global.var)

# Guesser guessed a letter
@socket_io.on("guessed_letter")
def guessed_letter(data:dict):
    letter_guessed = data["letter_guessed"]

    # Check if it has already been guessed
    if letter_guessed in guessed_letters_global.var:
        socket_io.emit("letter_has_already_been_guessed", room = guesser_id_global.var)
        return

    # Append it to guessed letters list
    guessed_letters_global.var.append(letter_guessed)

    # Check if the letter is in the word
    if letter_guessed in game_word_global.var:
        correct = True
        # Set censored word to empty
        censored_word = ""
        # Iterate through each letter in the word
        for letter_word in game_word_global.var:
            # Iterate through every guessed letter
            for letter_guessed in guessed_letters_global.var:
                # Add to censored word
                if letter_guessed == letter_word: 
                    censored_word += letter_guessed
                    break
            else:
                censored_word += "-"

        censored_game_word_global.var = censored_word
    
        # Check if the word has been guessed
        if game_word_global.var == censored_word:
            # Emit game won
            log(text_to_log = f"The guesser won! | {get_current_time()}")
            socket_io.emit("game_over_guesser_won", data = {"word": game_word_global.var}, broadcast = True)
            return

    # Letter wasn't in word, decrease guess
    else:
        correct = False
        guesses_left.change(by = -1)

        # Check if game over
        if guesses_left.get() <= 0:
            # Emit game over
            log(text_to_log = f"The guesser ran out of guesses! | {get_current_time()}")
            socket_io.emit("game_over_out_of_guesses", data = {"word": game_word_global.var}, broadcast = True)
            return


    # Give back the censored word
    log(text_to_log = f"A letter has been guessed! | Correct: {correct} | Data: {data} | {get_current_time()}")
    socket_io.emit("letter_has_been_guessed", {"letter_guessed": letter_guessed, "censored_word": censored_game_word_global.var, "guesses_left": guesses_left.get(), "correct": correct}, broadcast = True)

# User connection handler
@socket_io.on("user_connection")
def user_connect_handler(data:dict):
    # If the username check failed, close the connection. 
    # This most likely happens when the back button is pressed.
    if not check_username(username = data["username"]): 
        # Before we disconnect them, try to send them back to the main page
        socket_io.emit("redirect", {"new_url": "/"}, room = flask.request.sid)
        return

    users_connected.change(by = 1)
    send_message(message = f"{data['username']} has joined the game! There are now {users_connected.get()}/2 users in the game.")
    # Add to database
    user_database[flask.request.sid] = data["username"]

    log(text_to_log = f"{flask.request.sid}: {data['username']} joined | Database: {user_database} | {get_current_time()}")

    # If there are more than two people, get the host.
    all_user_ids = list(user_database.keys())
    if len(all_user_ids) >= 2: start_game(executioner_id = all_user_ids[0], guesser_id = all_user_ids[1])

# User disconnection handler
@socket_io.on("disconnect")
def user_disconnection_handler():
    # Get username
    try: username = user_database[flask.request.sid]
    # Username wasn't in database, so just exit
    except KeyError: return
    send_message(message = f"{username} has left the game! There are now {users_connected.get()} users in this game.")
    # Remove from database
    del user_database[flask.request.sid]

    # If there is a disconnect while the game has started, end the game.
    if started_global.var:
        socket_io.emit("end_game_disconnect", broadcast = True)
        # Reset variables
        reset_variables()
    else: 
        users_connected.change(by = -1)
        # Fix underflow error because my code is bad and calls reset twice when game ends
        if users_connected.get() < 0: users_connected.count = 0

    log(text_to_log = f"{flask.request.sid}: {username} left | Database: {user_database} | {get_current_time()}")

# Send message handler
@socket_io.on("send_message")
def send_message_handler(data:dict):
    messages_sent.change(by = 1)
    message = escape_html(text = data["message"])
    send_message(message = f"[#{str(messages_sent.get()).zfill(4)}] {user_database[flask.request.sid]}: {message}")

    log(text_to_log = f"{flask.request.sid}: {user_database[flask.request.sid]} sent message with data: \"{data}\" | {get_current_time()}")

# Message handler
@socket_io.on("message")
def message_handler(message:str):
    print(f"Message recieved at {datetime.datetime.utcnow()} (GMT): \"{message}\"")
    send_message(message = message)

    log(text_to_log = f"Sending message to all: {message} | {get_current_time()}")

# Website navigation ==============================================================================

# Errors
# 404 - Page not found
@main_app.errorhandler(404)
def page_not_found(error):
    return flask.render_template("page_not_found.html"), 404

# 500 - Internal server error
@main_app.errorhandler(500)
def internal_server_error(error):
    return flask.render_template("internal_server_error.html"), 500

# Join game
@main_app.route("/")
def join_game(): return flask.render_template("join.html")

# Hangman game
@main_app.route("/hangman", methods = ["POST", "GET"])
def hangman():
    try: username = flask.request.form["username_input"]
    # Username was not entered (either that or GET request)
    except KeyError: return flask.redirect("/")
    
    # Check username
    if not check_username(username = username): return flask.redirect("/")

    # Didn't return means the username was good, send to the hangman page.
    return flask.render_template("hangman.html", username = username, ip_address = IP_ADDRESS, port = PORT)

# Run
if __name__ == "__main__":
    socket_io.run(main_app, host = "127.0.0.1", port = 5000, debug = True) # Local, debug
    # socket_io.run(main_app, host = "127.0.0.1", port = 5000, debug = False) # Local, no debug
    # socket_io.run(main_app, debug = False, host = "0.0.0.0", port = PORT) # Production