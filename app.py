import configparser
import logging
import os
import threading
import time
from datetime import datetime, timedelta
from telegram import Update
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext
from pymongo import MongoClient
import requests
import hashlib

# Configure logging
logging.basicConfig(
    filename='bot_activity.log',  # Log file name
    level=logging.INFO,           # Set the logging level
    format='%(asctime)s - %(message)s'
)

# Global set to track logged-in users
logged_in_users = {}

# Load configuration
config = configparser.ConfigParser()
config.read('config.ini')

# MongoDB setup
connection_string = config['DATABASE']['CONNECTION_STRING']
db_name = config['DATABASE']['DB_NAME']
collection_name = config['DATABASE']['COLLECTION_NAME']

# MongoDB connection
client = MongoClient(connection_string)
db = client[db_name]
users_collection = db[collection_name]

# Hashing function for passwords
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

# Function to log out inactive users
def check_inactive_users():
    while True:
        now = datetime.now()
        to_logout = []

        # Identify users inactive for more than 3 minutes
        for chat_id, last_activity in logged_in_users.items():
            if now - last_activity > timedelta(minutes=1):
                to_logout.append(chat_id)

        # Log out inactive users
        for chat_id in to_logout:
            logged_in_users.pop(chat_id, None)
            print(f"User {chat_id} logged out due to inactivity.")  # For debugging purposes

        # Check every minute
        time.sleep(60)

# Register command
def register(update: Update, context: CallbackContext):
    chat_id = update.message.chat_id
    
    # Check if the user is already logged in
    if chat_id in logged_in_users:
        update.message.reply_text("You are already logged in. If you want to register a new account, please log out first.")
        return
    
    args = context.args
    if len(args) != 2:
        update.message.reply_text("Usage: /register <username> <password>")
        return

    username, password = args
    
    if users_collection.find_one({"username": username}):
        update.message.reply_text("Username already exists. Please choose a different one.")
    else:
        hashed_password = hash_password(password)
        
        try:
            users_collection.insert_one({
                "username": username,
                "password": hashed_password,
                "created_at": datetime.now()
            })
        except Exception as e:
            update.message.reply_text(f"An error occurred: {e}")
            return
        # Log user as registered and update activity time
        chat_id = update.message.chat_id
        logged_in_users[chat_id] = datetime.now()  # Store their last activity time

        update.message.reply_text("Registration successful! You are now logged in.")

# Login command
def login(update: Update, context: CallbackContext):
    chat_id = update.message.chat_id
    
    # Check if the user is already logged in
    if chat_id in logged_in_users:
        update.message.reply_text("You are already logged in. No need to log in again.")
        return
    
    args = context.args
    if len(args) != 2:
        update.message.reply_text("Usage: /login <username> <password>")
        return

    username, password = args
    hashed_password = hash_password(password)
    user = users_collection.find_one({"username": username, "password": hashed_password})

    if user:
        chat_id = update.message.chat_id
        logged_in_users[chat_id] = datetime.now()  # Update activity time
        update.message.reply_text(
            f"Login successful! Welcome back, {username}.\n\n"
            "You can make the most of this chatbot by using the following commands:\n"
            "- /search: Investigate suspected scams or cyber pitfalls and assess the risk levels of phone numbers, emails, or websites.\n"
            "- /tips: Get practical advice on staying safe online.\n"
            "- /logout: Securely log out of your account.\n"
            "- Free text: Chat with the bot and explore topics using ChatGPT.\n\n"
            "Feel free to explore and stay alert online!"
        )
    else:
        update.message.reply_text("Invalid username or password. Please try again.")
    
# Function: Update user's activity on any command or message
def update_activity(update: Update, context: CallbackContext):
    chat_id = update.message.chat_id
    if chat_id in logged_in_users:
        logged_in_users[chat_id] = datetime.now()  # Update activity time

# Middleware: Block users who are not logged in
def require_login(func):
    def wrapper(update: Update, context: CallbackContext):
        chat_id = update.message.chat_id
        if chat_id not in logged_in_users:
            update.message.reply_text(
                "Welcome to the Suspected Scam / Cyber Pitfall chatbot! Please /register or /login to continue."
            )
            return
        return func(update, context)
    return wrapper

# Define the HKBU_ChatGPT class
class HKBU_ChatGPT:
    def __init__(self, config_='./config.ini'):
            if type(config_) == str:
                self.config = configparser.ConfigParser()
                self.config.read(config_)
            elif type(config_) == configparser.ConfigParser:
                self.config = config_
    def submit(self, message):
        conversation = [{"role": "user", "content": message}]
        url = f"{self.config['CHATGPT']['BASICURL']}/deployments/{self.config['CHATGPT']['MODELNAME']}/chat/completions/?api-version={self.config['CHATGPT']['APIVERSION']}"
        headers = {
            'Content-Type': 'application/json',
            'api-key': self.config['CHATGPT']['ACCESS_TOKEN']
        }
        payload = {'messages': conversation}
        response = requests.post(url, json=payload, headers=headers)
        if response.status_code == 200:
            data = response.json()
            return data['choices'][0]['message']['content']
        else:
            return f"Error: {response.status_code}"

# Example commands wrapped with login enforcement
@require_login
def equipped_chatgpt(update, context):
    # Check if the user is logged in (enforced by require_login middleware)
    chat_id = update.message.chat_id
    
    # Retrieve the user's message from the Telegram chat
    user_message = update.message.text

    # Use the HKBU_ChatGPT instance to process the user's message
    try:
        # Pass the user's message to the ChatGPT class for processing
        update_activity(update, context)
        reply = chatgpt.submit(user_message)
        update.message.reply_text(reply)  # Send the response back to the user
    except Exception as e:
        update.message.reply_text(f"An error occurred while processing your request: {e}")


@require_login
def search(update: Update, context: CallbackContext) -> None:
    """
    Provide a website link for users to perform their own search.

    Args:
        update (Update): The Telegram update object.
        context (CallbackContext): The Telegram callback context object.
    """
    # Base URL for the Scameter search page
    base_url = "https://cyberdefender.hk/en-us/scameter/"

    # Message to send to the user with the link
    search_message = (
        "You can check the Scameter for risk levels here:\n"
        f"{base_url}\n\n"
        "Enter the relevant details (e.g., Phone, Email, or URL) on the site to perform your search."
    )

    # Send the message back to the user
    update.message.reply_text(search_message)

@require_login
def tips(update: Update, context: CallbackContext):
    # Define safety tips
    safety_tips = [
        "Be cautious when sharing personal information online.",
        "Verify the authenticity of links before clicking on them.",
        "Never provide sensitive information, such as passwords, to untrusted sources.",
        "Use strong and unique passwords for different accounts.",
        "Enable two-factor authentication (2FA) whenever possible.",
        "Be wary of unsolicited messages or calls requesting personal or financial information.",
        "Keep your devices and software updated to avoid vulnerabilities.",
        "Avoid using public Wi-Fi networks for sensitive transactions."
    ]
    
    # Format the tips into a readable message
    tips_message = "Here are some safety tips to protect yourself online:\n\n"
    tips_message += "\n".join([f"- {tip}" for tip in safety_tips])
    
    # Add resource links
    tips_message += (
        "\n\nAdditional resources:\n"
        "- Join our WhatsApp group: [Click here](https://www.whatsapp.com/channel/0029VaB5r1v2v1Ik0zC6xF3m)\n"
        "- Download the Apple app: [Click here](https://apps.apple.com/hk/app/%E9%98%B2%E9%A8%99%E8%A6%96%E4%BC%8Fapp/id1663109821)\n"
        "- Download the Android app: [Click here](https://play.google.com/store/apps/details?id=scameter.hk.cyberdefender&pli=1)"
    )
    
    # Send the tips and resources to the user
    update.message.reply_text(tips_message)
    
@require_login        
def logout(update: Update, context: CallbackContext):
    # Extract chat_id
    chat_id = update.message.chat_id
    
    # Check if the user is logged in
    if chat_id in logged_in_users:
        # Remove the user from the logged_in_users dictionary
        del logged_in_users[chat_id]
        
        update.message.reply_text("You have been successfully logged out. Stay safe online!")
    else:
        # If the user is not logged in
        update.message.reply_text("You are not logged in. Please log in first using /login.")



def main():
    global chatgpt, logged_in_users
    
    logged_in_users = {}  # Clear all users on restart
    logging.info("Server started. All users have been logged out.")
    # Initialize HKBU_ChatGPT instance
    chatgpt = HKBU_ChatGPT(config)
    
    # Initialize bot token from environment variable
    updater = Updater(token=(config['TELEGRAM']['ACCESS_TOKEN']), use_context=True)
    dispatcher = updater.dispatcher

    # Allow only /register and /login without authentication
    dispatcher.add_handler(CommandHandler("register", register))
    dispatcher.add_handler(CommandHandler("login", login))

    # Protect all other commands and text messages with login enforcement
    dispatcher.add_handler(CommandHandler("search", require_login(search)))
    dispatcher.add_handler(CommandHandler("tips", require_login(tips)))
    dispatcher.add_handler(CommandHandler("logout", require_login(logout)))
    
    dispatcher.add_handler(MessageHandler(Filters.text & (~Filters.command), require_login(equipped_chatgpt)))
    # Start the inactivity checker thread
    inactivity_thread = threading.Thread(target=check_inactive_users, daemon=True)
    inactivity_thread.start()
    
    # Start the bot
    try:
        updater.start_polling()
    except Exception as e:
        print(f"Error occurred: {e}")
    updater.idle()

if __name__ == '__main__':
    main()