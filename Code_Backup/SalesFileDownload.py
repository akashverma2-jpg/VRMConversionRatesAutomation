import os
from imap_tools import MailBox, AND

# Load .env file if it exists
def load_env():
    current_dir = os.path.dirname(os.path.abspath(__file__))
    for d in [os.getcwd(), current_dir, os.path.dirname(current_dir)]:
        env_path = os.path.join(d, '.env')
        if os.path.exists(env_path):
            with open(env_path) as f:
                for line in f:
                    if '=' in line:
                        key, val = line.strip().split('=', 1)
                        os.environ[key] = val.strip().strip('"').strip("'")
            break

load_env()

# --- CONFIGURATION ---
HOST = 'imap.gmail.com'
USERNAME = 'akash.verma2@turtlemint.com'
PASSWORD = os.environ.get('GMAIL_APP_PASSWORD', '')
SEARCH_STRING = 'VRM'
DOWNLOAD_FOLDER = './downloads'

if not os.path.exists(DOWNLOAD_FOLDER):
    os.makedirs(DOWNLOAD_FOLDER)

def download_latest_attachment():
    print("Connecting to Gmail...")
    try:
        with MailBox(HOST).login(USERNAME, PASSWORD, 'INBOX') as mailbox:
            # reverse=True looks at the newest emails first
            for msg in mailbox.fetch(AND(subject=SEARCH_STRING), reverse=True):
                # Check that 'sale' and 'file' are in the subject (case-insensitive)
                subject_lower = msg.subject.lower()
                if 'sale' in subject_lower and 'file' in subject_lower:
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