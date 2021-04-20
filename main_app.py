# Import
import flask
import flask_socketio
import datetime
import json

# Counter class
class Counter:
    def __init__(self, initial_value:int = 0): self.count = initial_value
    def change(self, by:int = 1): self.count += by
    def get(self): return self.count

# Setup
with open ("config.json") as config_file:
    config_dict = json.load(config_file)
    SECRET_KEY = config_dict["secret_key"]
    LOG_LOCATION = config_dict["log_location"]
    UTC_TIMEZONE_OFFSET = config_dict["utc-timezone-offset"]
    GUESSES = config_dict["guesses"]

main_app = flask.Flask(__name__, template_folder = "template")
main_app.config["SECRET_KEY"] = SECRET_KEY
socket_io = flask_socketio.SocketIO(main_app)
users_connected = Counter(initial_value = 0)
messages_sent = Counter(initial_value = 0)
guesses_left = Counter(initial_value = GUESSES)
user_database = {}

# Misc. functions =================================================================================

# Log
def log(text_to_log:str, file:str = LOG_LOCATION):
    print(text_to_log)
    with open (file = LOG_LOCATION, mode = "a") as log_text_file: log_text_file.write(text_to_log + "\n")

# Get current time (shifted to timezone)
def get_current_time():
    return (datetime.datetime.utcnow() + datetime.timedelta(hours = UTC_TIMEZONE_OFFSET)).strftime("%m/%d/%Y")

# Hangman functions ===============================================================================

# Send message
def send_message(message): flask_socketio.send(message, broadcast = True)

# User connection handler
@socket_io.on("user_connection")
def user_connect_handler(data:dict):
    users_connected.change(by = 1)
    send_message(message = f"{data['username']} has joined the game! There are now {users_connected.get()}/2 users in the game.")
    # Add to database
    user_database[flask.request.sid] = data["username"]

    log(text_to_log = f"{flask.request.sid}: {data['username']} joined | Database: {user_database} | {get_current_time()}")

# User disconnection handler
@socket_io.on("disconnect")
def user_disconnection_handler():
    username = user_database[flask.request.sid]
    users_connected.change(by = -1)
    send_message(message = f"{username} has left the game! There are now {users_connected.get()} users in this game.")
    # Remove from database
    del user_database[flask.request.sid]

    log(text_to_log = f"{flask.request.sid}: {username} left | Database: {user_database} | {get_current_time()}")

# Send message handler
@socket_io.on("send_message")
def send_message_handler(data:dict):
    messages_sent.change(by = 1)
    send_message(message = f"[#{str(messages_sent.get()).zfill(4)}] {user_database[flask.request.sid]}: {data['message']}")

    log(text_to_log = f"{flask.request.sid}: {user_database[flask.request.sid]} sent message with data: \"{data}\" | Database: {user_database} | {get_current_time()}")

# Message handler
@socket_io.on("message")
def message_handler(message:str):
    print(f"Message recieved at {datetime.datetime.utcnow()} (GMT): \"{message}\"")
    send_message(message = message)

    log(text_to_log = f"Sending message to all: {message} | {get_current_time()}")

# Website navigation ==============================================================================

# Join game
@main_app.route("/")
def join_game(): return flask.render_template("join.html")

# Hangman game
@main_app.route("/hangman", methods = ["POST", "GET"])
def hangman():
    # Make sure the game is not full already
    if len(user_database) < 2:
        # Send to hangman game with username
        try:
            # Get username
            username = flask.request.form["username_input"]
            # Make sure username is not already in database
            for username_db in user_database.values():
                if username_db.lower() == username.lower():
                    flask.flash(f"Username \"{username_db}\" is already in use.")
                    break
            else: return flask.render_template("hangman.html", username = username)

        # Either a GET request username not submitted
        except Exception: pass
    
    # Game is full
    else: flask.flash("This game is full. Sorry!")

    # If haven't returned, then just send back to join
    return flask.redirect("/")

# Run
if __name__ == "__main__":
    socket_io.run(main_app, debug = True)