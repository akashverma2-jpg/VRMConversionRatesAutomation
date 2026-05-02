import os
from imap_tools import MailBox, AND

# --- CONFIGURATION ---
HOST = 'imap.gmail.com'
USERNAME = 'akash.verma2@turtlemint.com'
PASSWORD = os.environ.get('GMAIL_APP_PASSWORD', 'your_app_password_here') # Use env var or replace locally 
SEARCH_STRING = 'VRM Sale file'
DOWNLOAD_FOLDER = './downloads'

if not os.path.exists(DOWNLOAD_FOLDER):
    os.makedirs(DOWNLOAD_FOLDER)

def download_latest_attachment():
    print("Connecting to Gmail...")
    try:
        with MailBox(HOST).login(USERNAME, PASSWORD, 'INBOX') as mailbox:
            # reverse=True looks at the newest emails first
            for msg in mailbox.fetch(AND(subject=SEARCH_STRING), reverse=True):
                # We check every email, but we only "log" the winner below
                for att in msg.attachments:
                    if att.filename.endswith(('.xlsx', '.xls')):
                        file_path = os.path.join(DOWNLOAD_FOLDER, att.filename)
                        with open(file_path, 'wb') as f:
                            f.write(att.payload)
                        
                        # --- UPDATED LOGGING ---
                        print("-" * 30)
                        print(f"✅ ATTACHMENT FOUND!")
                        print(f"📧 Subject: {msg.subject}")
                        print(f"📅 Date:    {msg.date}")
                        print(f"📁 File:    {att.filename}")
                        print("-" * 30)
                        
                        return file_path
        
        print("❌ No Excel attachment found in matching emails.")
    except Exception as e:
        print(f"An error occurred: {e}")
    return None

if __name__ == "__main__":
    download_latest_attachment()