"""
test_email.py — Test script to verify Gmail SMTP credentials delivery.
Usage:
    python test_email.py [optional_recipient_email]
"""

import sys
import os
import base64
from dotenv import load_dotenv

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

# Load .env
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

MAIL_SERVER   = os.getenv("MAIL_SERVER", "smtp.gmail.com")
MAIL_PORT     = int(os.getenv("MAIL_PORT", 587))
MAIL_USERNAME = os.getenv("MAIL_USERNAME", "").strip()
MAIL_PASSWORD = os.getenv("MAIL_PASSWORD", "").strip()
MAIL_FROM     = os.getenv("MAIL_FROM", MAIL_USERNAME).strip()

recipient = sys.argv[1].strip() if len(sys.argv) > 1 else MAIL_USERNAME

print("=" * 60)
print("Attendance Geo Tracker - Email Delivery Verification")
print("=" * 60)
print(f"SMTP Server : {MAIL_SERVER}:{MAIL_PORT}")
print(f"Sender      : {MAIL_FROM}")
print(f"Username    : {MAIL_USERNAME}")
print(f"Recipient   : {recipient}")
print("=" * 60)

if not MAIL_USERNAME or not MAIL_PASSWORD:
    print("[ERROR] MAIL_USERNAME or MAIL_PASSWORD missing in .env")
    sys.exit(1)

clean_password = MAIL_PASSWORD.replace(" ", "")

subject = "Test: Attendance Geo Tracker Credentials Delivery"
plain_body = f"""Hello,

This is a test verifying that the Attendance Geo Tracker email delivery system is working.

Sample Student Login Credentials:
Email: {recipient}
Password: SamplePassword123

Please keep your login credentials secure.

Best regards,
Attendance Geo Tracker Team
"""

html_body = f"""<!doctype html>
<html>
<body style="font-family: Arial, sans-serif; background: #f4f6fb; padding: 20px; margin: 0;">
  <div style="max-width: 580px; margin: 20px auto; background: #ffffff; border-radius: 10px; box-shadow: 0 4px 18px rgba(0,0,0,0.08); overflow: hidden;">
    <div style="background: linear-gradient(90deg, #667eea, #764ba2); color: #fff; padding: 22px 28px;">
      <h2 style="margin: 0; font-size: 20px;">Attendance Geo Tracker</h2>
    </div>
    <div style="padding: 24px 28px; color: #0f1724;">
      <p style="font-size: 16px; margin-top: 0;">Hello,</p>
      <p style="color: #4b5563; line-height: 1.5;">Your email delivery system is working! When students are enrolled, they receive an email with their one-time access credentials like below:</p>
      <div style="background: #f8fafc; border-left: 4px solid #667eea; padding: 14px 18px; border-radius: 6px; margin: 18px 0;">
        <p style="margin: 0 0 8px;"><strong>Student Email:</strong> <code>{recipient}</code></p>
        <p style="margin: 0;"><strong>One-Time Password:</strong> <code>SamplePassword123</code></p>
      </div>
      <p style="color: #4b5563; font-size: 14px;">Students use these credentials to log into the mobile/web attendance portal and scan classroom QR codes.</p>
    </div>
    <div style="padding: 16px 28px; background: #f9fafb; border-top: 1px solid #e5e7eb; font-size: 12px; color: #9ca3af;">
      Attendance Geo Tracker Automated System
    </div>
  </div>
</body>
</html>"""

print("\n1. Connecting to smtp.gmail.com:587...")
try:
    server = smtplib.SMTP(MAIL_SERVER, MAIL_PORT, timeout=15)
    server.ehlo()
    print("2. Starting TLS encryption...")
    server.starttls()
    server.ehlo()
    
    print("3. Authenticating with Gmail...")
    auth_str = f"\0{MAIL_USERNAME}\0{clean_password}".encode('ascii')
    code, resp = server.docmd("AUTH", "PLAIN " + base64.b64encode(auth_str).decode('ascii'))
    
    if code != 235:
        print(f"\n[FAILED] Gmail rejected credentials! Code: {code}")
        print(f"Message from Google: {resp.decode('utf-8', errors='ignore')}")
        print("\n--> Why this happened:")
        print("Google says 535 BadCredentials. This means the 16-character App Password")
        print(f"'{clean_password}' is either incorrect, revoked, or belongs to another Google account.")
        print("\n--> How to resolve:")
        print("1. Go to https://myaccount.google.com/apppasswords while logged in as shashidharpc1012@gmail.com")
        print("2. Generate a new App Password (select App: 'Mail', Device: 'Other' -> Name it 'GeoTracker')")
        print("3. Paste the newly generated 16 characters into backend/.env (MAIL_PASSWORD=...)")
        server.close()
        sys.exit(1)

    print("   -> Authentication succeeded!")

    print(f"4. Sending test email to {recipient}...")
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"Attendance Geo Tracker <{MAIL_FROM}>"
    msg["To"] = recipient
    msg.attach(MIMEText(plain_body, "plain"))
    msg.attach(MIMEText(html_body, "html"))

    server.sendmail(MAIL_FROM, [recipient], msg.as_string())
    server.quit()
    print(f"\n[SUCCESS] Test email successfully delivered to {recipient}!")
    print("Please check your Gmail inbox (and Spam/Promotions folder).")

except Exception as e:
    print(f"\n[FAILED] Connection error: {e}")
