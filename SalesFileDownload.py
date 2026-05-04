import os
from imap_tools import MailBox
from datetime import datetime, timedelta

# --- CONFIGURATION ---
HOST = 'imap.gmail.com'
USERNAME = 'akash.verma2@turtlemint.com'
PASSWORD = 'zaqw aqzu hpfs spha'
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

        # 🔥 FETCH BROAD (NO FILTERS)
        messages = list(mailbox.fetch(reverse=True, limit=100))

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
                tokens = [TARGET_MONTH.lower(), 'sale']
                print(f"🔍 CATCH-UP MODE: {TARGET_MONTH}")
            else:
                tokens = [datetime.now().strftime('%B').lower(), 'sale']
                print(f"🔍 REGULAR MODE")

            filtered = []

            for msg in messages:
                if not sender_match(msg.from_):
                    continue

                subject = (msg.subject or "").lower()

                if all(token in subject for token in tokens):
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