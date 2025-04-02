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

# MongoDB setup
connection_string = (os.environ['DATABASE_CONNECTION_STRING'])
db_name = (os.environ['DATABASE_DB_NAME'])
collection_name_users = (os.environ['DATABASE_COLLECTION_NAME_USERS'])
collection_name_login_logs = (os.environ['DATABASE_COLLECTION_NAME_LOGIN_LOGS'])
collection_name_chat = (os.environ['DATABASE_COLLECTION_NAME_CHAT'])

# MongoDB connection
client = MongoClient(connection_string)
db = client[db_name]
users_collection = db[collection_name_users]
login_logs_collection = db[collection_name_login_logs]
chat_collection = db[collection_name_chat]

menu = ("You can make the most of this chatbot by using the following commands👇🏻:\n"
        "- /search: Investigate suspected scams or cyber pitfalls and assess the risk levels of phone numbers, emails, or websites.\n"
        "- /tips: Get practical advice on staying safe online.\n"
        "- /history: Get recent 10 search history\n"
        "- /logout: Securely log out of your account.\n"
        "- 📝Free text: Chat with the bot and explore topics using ChatGPT.\n\n"
        "Feel free to explore and stay alert online!🚨")

# Hashing function for passwords
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def check_login_status(update,username):
    try:
        countLogin = login_logs_collection.count_documents({"username":username, "status": "logged in"})
        if countLogin >= 1:
            return True
        else:
            return False
    except Exception as e:
        update.message.reply_text(f"An error occurred: {e}")
        return

def check_chat_id_username(update,chat_id):
    try:
        countLogin = login_logs_collection.count_documents({"chat_id":chat_id, "status": "logged in"})
        if countLogin >= 1:
            document = login_logs_collection.find_one({"status": "logged in", "chat_id": chat_id})
            username = document["username"]
            return username 
        else:
            return
    except Exception as e:
        update.message.reply_text(f"An error occurred: {e}")
        return

# Function to log out inactive users
def check_inactive_users():
    while True:
        now = datetime.now()
        to_logout = []
        
         # Identify users inactive for more than 1 minute
        for document in login_logs_collection.find({"status": "logged in"}):
            last_activity = document["last_activity"]
            if now - last_activity > timedelta(minutes=1):
                to_logout.append(document["_id"])
        # Log out inactive users
        for _id in to_logout:
            login_logs_collection.update_one(
                {"_id": _id},
                {"$set": {"status": "logged out"}}
            )
        # Check every minute
        time.sleep(60)

# Register command
def register(update: Update, context: CallbackContext):
    chat_id = update.message.chat_id
    username = check_chat_id_username(update,chat_id)
    # Check if the user is already logged in
    if check_login_status(update,username):
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
        login_logs_collection.insert_one({
            "username": username,
            "chat_id": chat_id,
            "action": "login",
            "timestamp": datetime.now(),
            "last_activity": datetime.now(),
            "status": "logged in"
        })

        update.message.reply_text("Registration successful! You are now logged in👏🏻\n\n"
        +menu)

# Login command
def login(update: Update, context: CallbackContext):
    chat_id = update.message.chat_id
    username = check_chat_id_username(update,chat_id)
    # Check if the user is already logged in
    if check_login_status(username):
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
        # Insert login activity into MongoDB
        login_logs_collection.insert_one({
            "username": username,
            "chat_id": chat_id,
            "action": "login",
            "timestamp": datetime.now(),
            "last_activity": datetime.now(),
            "status": "logged in"
        })
        update.message.reply_text(
            f"Login successful! Welcome back, {username}☺️\n\n"
            +menu
        )
    else:
        update.message.reply_text("Invalid username or password. Please try again.")
    
# Function: Update user's activity on any command or message
def update_activity(update: Update, context: CallbackContext):
    chat_id = update.message.chat_id
    username = check_chat_id_username(update,chat_id)
    if check_login_status(username):
        UpdateActivity = []
        for document in login_logs_collection.find({"username": username, "status": "logged in"}):
                UpdateActivity.append(document["_id"])
        for _id in UpdateActivity:
            login_logs_collection.update_one(
                {"_id": _id},
                {"$set": {"last_activity": datetime.now()}}
            )

# Middleware: Block users who are not logged in
def require_login(func):
    def wrapper(update: Update, context: CallbackContext):
        try:
            chat_id = update.message.chat_id
            username = check_chat_id_username(update,chat_id)
            if check_login_status(username)==False:
                update.message.reply_text(
                    "Welcome to the Suspected Scam / Cyber Pitfall chatbot! Please /register or /login to continue."
                )
                return
            return func(update, context)
        except Exception as e:
            update.message.reply_text(f"An error occurred: {e}")
            return
    return wrapper

# Define the HKBU_ChatGPT class
class HKBU_ChatGPT:
    def __init__(self):
        self.basic_url = os.environ.get('CHATGPT_BASICURL')
        self.model_name = os.environ.get('CHATGPT_MODELNAME')
        self.api_version = os.environ.get('CHATGPT_APIVERSION')
        self.access_token = os.environ.get('CHATGPT_ACCESS_TOKEN')
    def submit(self, message):
        system_message = {
            "role": "system",
            "content": "You are an expert in identifying and discussing scams. Only provide information related to scams."
        }
        conversation = [system_message,{"role": "user", "content": message}]
        url = f"{self.basic_url}/deployments/{self.model_name}/chat/completions/?api-version={self.api_version}"
        headers = {
            'Content-Type': 'application/json',
            'api-key': self.access_token 
        }
        payload = {'messages': conversation}
        response = requests.post(url, json=payload, headers=headers)
        if response.status_code == 200:
            data = response.json()
            chatgpt_response = data['choices'][0]['message']['content']

            return chatgpt_response
        else:
            return f"Error: {response.status_code}"

# Example commands wrapped with login enforcement
@require_login
def equipped_chatgpt(update, context):
    # Check if the user is logged in (enforced by require_login middleware)
    chat_id = update.message.chat_id
    username = check_chat_id_username(chat_id)
    
    # Retrieve the user's message from the Telegram chat
    user_message = update.message.text

    # Use the HKBU_ChatGPT instance to process the user's message
    try:
        # Pass the user's message to the ChatGPT class for processing
        update_activity(update, context)
        reply = chatgpt.submit(user_message)
        update.message.reply_text(reply)  # Send the response back to the user
        # Limit the response to 30 words
        words = reply.split()
        if len(words) > 30:
            limited_response = " ".join(words[:30]) + "..." 
        else:
            limited_response = reply        
        # Check the count of record of the user in the collection
        query = {"username": username}
        record_count = chat_collection.count_documents(query)
        # If the count is greater than or equal to 10, delete the oldest record
        if record_count >= 10:
            # Find the oldest record based on a timestamp field
            # Replace 'timestamp_field' with the actual field name that stores the timestamp
            oldest_record = chat_collection.find_one(query, sort=[("_id", 1)])
            
            if oldest_record:
                # Delete the oldest record
                chat_collection.delete_one({'_id': oldest_record['_id']})
                print(f"Deleted record with _id: {oldest_record['_id']}")
            else:
                print("No record found to delete.")
        else:
            print("Record count is less than 10. No deletion performed.")

        # Record the interaction in MongoDB
        chat_collection.insert_one({
            "chat_id": chat_id,
            "username": username,
            "user_message": user_message,
            "chatgpt_response": reply,
            "timestamp": datetime.now()
        })
    except KeyError:
        # Handle cases where the chat ID is not found in logged_in_users
        update.message.reply_text("An error occurred: You are not logged in or your session has expired.")
    except Exception as e:
        # Handle unexpected errors and inform the user
        update.message.reply_text(f"An error occurred while processing your request: {e}")

@require_login
def chatHistory(update, context: CallbackContext):
    # Check if the user is logged in (enforced by require_login middleware)
    chat_id = update.message.chat_id
    username = check_chat_id_username(chat_id)
    try:
        query = {"username": username}
        record_count = chat_collection.count_documents(query)
        if record_count==0:
            update.message.reply_text("You have no search history found.")
        else:
            records = chat_collection.find(query).sort("_id",1).limit(10)
            # Extract user_message into a list and format them
            user_messages = [f"{i+1}. {record["user_message"]}" for i, record in enumerate(records)]
            for message in user_messages:
                update.message.reply_text(message)
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
    username = check_chat_id_username(chat_id)
    
    # Check if the user is logged in
    if check_login_status(username):
        # Insert logout activity into MongoDB
        login_logs_collection.insert_one({
            "username": username,
            "chat_id": chat_id,
            "action": "logout",
            "timestamp": datetime.now(),
            "last_activity": datetime.now(),
            "status": "logged out"
        })
        Logout = []
        for document in login_logs_collection.find({"username": username, "status": "logged in"}):
                Logout.append(document["_id"])
        for _id in Logout:
            login_logs_collection.update_one(
                {"_id": _id},
                {"$set": {"last_activity": datetime.now(), "status":"logged out"}}
            )
        
        
        update.message.reply_text("You have been successfully logged out. Stay safe online!")
    else:
        # If the user is not logged in
        update.message.reply_text("You are not logged in. Please log in first using /login.")



def main():
    global chatgpt
    
    # Initialize HKBU_ChatGPT instance
    chatgpt = HKBU_ChatGPT()
    
    # Initialize bot token from environment variable
    updater = Updater(token=(os.environ['ACCESS_TOKEN']), use_context=True)
    dispatcher = updater.dispatcher

    # Allow only /register and /login without authentication
    dispatcher.add_handler(CommandHandler("register", register))
    dispatcher.add_handler(CommandHandler("login", login))

    # Protect all other commands and text messages with login enforcement
    dispatcher.add_handler(CommandHandler("search", require_login(search)))
    dispatcher.add_handler(CommandHandler("tips", require_login(tips)))
    dispatcher.add_handler(CommandHandler("history", require_login(chatHistory)))
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