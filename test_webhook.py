import requests
import os

def load_webhook():
    if os.path.exists("webhook.txt"):
        with open("webhook.txt", "r") as f:
            url = f.read().strip()
            if url:
                return url
    return os.getenv("DISCORD_WEBHOOK", "")

def test_webhook(url):
    if not url:
        print("❌ No webhook found. Add webhook.txt or set DISCORD_WEBHOOK env variable.")
        return

    data = {
        "embeds": [{
            "title": "✅ Webhook Test",
            "description": "Webhook is working correctly!",
            "color": 3066993,
            "footer": {"text": "Roblox Checker"}
        }]
    }

    try:
        response = requests.post(url, json=data, timeout=5)
        if response.status_code == 204:
            print("✅ Webhook works! Check your Discord channel.")
        else:
            print(f"❌ Webhook returned status {response.status_code}: {response.text}")
    except Exception as e:
        print(f"❌ Failed to send: {e}")

if __name__ == "__main__":
    webhook = load_webhook()
    test_webhook(webhook)
