import os
from imap_tools import MailBox
from datetime import datetime, timedelta

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
DOWNLOAD_FOLDER = './downloads'

SENDERS = ['istiyak.q9@turtlemint.com', 'anant.dharme@turtlemint.com']

TARGET_MONTH = os.getenv("TARGET_MONTH")
SUBJECT_KEYWORD = os.getenv("SUBJECT_KEYWORD")
RECEIVED_DATE = os.getenv("RECEIVED_DATE")


def build_tokens(text):
    return text.replace("'", "").lower().split() if text else []


def sender_match(msg_from):
    msg_from = (msg_from or "").lower()
    return any(sender in msg_from for sender in SENDERS)


def download_latest_attachment():
    print(f"📡 Connecting to {HOST}...")

    with MailBox(HOST).login(USERNAME, PASSWORD) as mailbox:

        # 🔥 FETCH FILTERED (BY AUTHORIZED SENDERS)
        # Using raw IMAP search criteria to ensure compatibility with Gmail's IMAP search engine
        sender_criteria = 'OR FROM "istiyak.q9@turtlemint.com" FROM "anant.dharme@turtlemint.com"'
        messages = list(mailbox.fetch(criteria=sender_criteria, reverse=True, limit=100))

        if not messages:
            print("❌ No emails found in inbox.")
            return None

        # =========================================================
        # 🔍 MANUAL MODE
        # =========================================================
        if SUBJECT_KEYWORD and RECEIVED_DATE:
            try:
                search_date = datetime.strptime(RECEIVED_DATE, '%d-%b-%Y').date()
                tokens = build_tokens(SUBJECT_KEYWORD)

                print(f"🔍 MANUAL SEARCH: Tokens={tokens} | Date={RECEIVED_DATE}")

                filtered = []

                for msg in messages:
                    if not sender_match(msg.from_):
                        continue

                    msg_date = msg.date.date()
                    subject = (msg.subject or "").lower()

                    # date filter
                    if not (search_date - timedelta(days=1) <= msg_date <= search_date + timedelta(days=1)):
                        continue

                    # subject filter
                    if all(token in subject for token in tokens):
                        filtered.append(msg)

                if not filtered:
                    print("❌ No email matched after filtering.")
                    return None

                messages = filtered

            except ValueError:
                print("❌ Invalid date format.")
                return None

        # =========================================================
        # ⚡ AUTO MODE
        # =========================================================
        else:
            if TARGET_MONTH:
                month_str = TARGET_MONTH.lower()
                print(f"🔍 CATCH-UP MODE: {TARGET_MONTH}")
            else:
                month_str = datetime.now().strftime('%B').lower()
                print(f"🔍 REGULAR MODE")

            short_month = month_str[:3]
            filtered = []

            for msg in messages:
                if not sender_match(msg.from_):
                    continue

                subject = (msg.subject or "").lower()

                # Check that 'sale' is present, and either the full month name or short month name is present
                if 'sale' in subject and (month_str in subject or short_month in subject):
                    filtered.append(msg)

            if not filtered:
                print("❌ No matching emails found.")
                return None

            messages = filtered

        # =========================================================
        # 🎯 PRIORITY (ANANT FIRST)
        # =========================================================
        selected = None

        for msg in messages:
            if 'anant.dharme@turtlemint.com' in (msg.from_ or "").lower():
                selected = msg
                break

        if not selected:
            selected = messages[0]

        print(f"📧 Selected: {selected.subject}")
        print(f"📨 From: {selected.from_}")
        print(f"📅 Date: {selected.date}")

        # =========================================================
        # 📥 DOWNLOAD
        # =========================================================
        if not os.path.exists(DOWNLOAD_FOLDER):
            os.makedirs(DOWNLOAD_FOLDER)

        for att in selected.attachments:
            if att.filename and att.filename.lower().endswith(('.xlsx', '.xls')):
                path = os.path.join(DOWNLOAD_FOLDER, att.filename)

                with open(path, 'wb') as f:
                    f.write(att.payload)

                print(f"✅ Downloaded: {att.filename}")
                return path

        print("⚠️ No Excel attachment found.")
        return None


if __name__ == "__main__":
    result = download_latest_attachment()
    if not result:
        exit(1)