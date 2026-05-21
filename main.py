import requests
import string
import itertools
import os
import time
import random
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock

def load_webhook():
    if os.path.exists("webhook.txt"):
        with open("webhook.txt", "r") as f:
            url = f.read().strip()
            if url:
                print("🔗 Webhook loaded from webhook.txt")
                return url
    url = os.getenv("DISCORD_WEBHOOK", "")
    if url:
        print("🔗 Webhook loaded from environment variable")
    else:
        print("⚠️ No webhook found, running without Discord notifications")
    return url

DISCORD_WEBHOOK = load_webhook()

NUM_THREADS  = 2
BATCH_SIZE   = 300
PROGRESS_FILE = "progress.txt"

lock = Lock()
rate_limited = False

def send_to_discord(username):
    if not DISCORD_WEBHOOK:
        return
    data = {
        "embeds": [{
            "title": "🎮 Available Roblox Username Found!",
            "description": f"**Username:** `{username}`",
            "color": 3447003,
            "fields": [{"name": "🔗 Direct Link", "value": f"https://www.roblox.com/search/users?keyword={username}", "inline": False}],
            "footer": {"text": "Roblox Checker"}
        }]
    }
    try:
        requests.post(DISCORD_WEBHOOK, json=data, timeout=5)
    except:
        pass

def load_usernames():
    if os.path.exists("words.txt") and os.path.getsize("words.txt") > 0:
        print("📖 Loading words.txt...")
        with open("words.txt", "r", encoding="utf-8") as f:
            return [l.strip() for l in f if 3 <= len(l.strip()) <= 20]
    else:
        print("📦 Generating all 4-character usernames...")
        chars = string.ascii_lowercase + string.digits + "_"
        result = []
        for p in itertools.product(chars, repeat=4):
            u = "".join(p)
            if not (u.startswith("_") or u.endswith("_")):
                result.append(u)
        return result

def load_progress():
    if os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE, "r") as f:
            try:
                return int(f.read().strip())
            except ValueError:
                return 0
    return 0

def save_progress(index):
    with open(PROGRESS_FILE, "w") as f:
        f.write(str(index))

def check_user(username):
    global rate_limited

    if rate_limited:
        return None  # skip, will retry this batch

    try:
        response = requests.post(
            "https://users.roblox.com/v1/usernames/users",
            json={"usernames": [username]},
            timeout=10
        )

        if response.status_code == 200:
            result = response.json()
            if result.get("data") and len(result["data"]) > 0:
                user_data = result["data"][0]
                if user_data.get("id") is not None:
                    print(f"❌ Taken: {username} (ID: {user_data['id']})")
                    return "taken"
            print(f"✅ AVAILABLE: {username}")
            send_to_discord(username)
            return "available"

        elif response.status_code == 429:
            with lock:
                if not rate_limited:
                    rate_limited = True
                    wait = random.randint(20, 30)
                    print(f"\n⚠️ Rate limited at '{username}'! Waiting {wait}s before retrying...")
            return "rate_limited"

        else:
            print(f"⚠️ Unexpected status {response.status_code} for {username}")
            return "error"

    except requests.exceptions.Timeout:
        print(f"⏱️ Timeout: {username}")
        return "error"
    except Exception as e:
        print(f"⚠️ Error on {username}: {e}")
        return "error"

def run_batch(batch):
    """Run a batch with threads. Returns how many were successfully processed."""
    global rate_limited
    rate_limited = False
    processed = 0

    with ThreadPoolExecutor(max_workers=NUM_THREADS) as executor:
        futures = {executor.submit(check_user, u): u for u in batch}
        for future in as_completed(futures):
            result = future.result()
            if result in ("taken", "available", "error"):
                processed += 1
            elif result == "rate_limited":
                # Don't count rate limited ones — they'll be retried
                pass

    return processed

def main():
    global rate_limited

    all_names = load_usernames()
    total = len(all_names)
    current_index = load_progress()

    if current_index >= total:
        print("🎉 All usernames have been scanned!")
        return

    print(f"🚀 Starting from index {current_index} / {total}")
    print(f"⚡ Threads: {NUM_THREADS} | Batch size: {BATCH_SIZE}\n")

    while current_index < total:
        end_index = min(current_index + BATCH_SIZE, total)
        batch = all_names[current_index:end_index]

        print(f"\n📡 Batch: {current_index} → {end_index} ({end_index - current_index} names)")

        rate_limited = False
        processed = run_batch(batch)

        if rate_limited:
            # Wait then retry the same batch
            wait = random.randint(20, 30)
            print(f"⏳ Cooling down {wait}s then retrying batch from {current_index}...")
            time.sleep(wait)
            continue  # retry same batch

        # Full batch done, advance
        current_index = end_index
        save_progress(current_index)
        print(f"💾 Progress saved: {current_index} / {total}")

    print("\n🎉 Scan complete!")

if __name__ == "__main__":
    main()
