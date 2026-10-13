"""Desktop alerts for the nightly job, using a Windows toast notification.

Usage:
  python -m jobs.notify     send a test notification, to check alerts work on this PC

Nothing here may break the job: if the notification can't be shown, that is logged and the job carries on.
"""
import logging
import os
import subprocess
import sys

log = logging.getLogger("refresh")

# Reads the text from environment variables, so quotes in a message can't break the PowerShell script.
# SetInnerText escapes anything XML-sensitive. The app id is Windows PowerShell's own, which is allowed to show toasts.
_TOAST_SCRIPT = r"""
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null
$xml = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02)
$text = $xml.GetElementsByTagName('text')
$text.Item(0).InnerText = $env:STOCKMARKET_ALERT_TITLE
$text.Item(1).InnerText = $env:STOCKMARKET_ALERT_BODY
$appId = '{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe'
$toast = [Windows.UI.Notifications.ToastNotification]::new($xml)
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($appId).Show($toast)
"""


def send_notification(title: str, body: str) -> bool:
    """Show a desktop notification. Returns True if Windows accepted it; never raises."""
    if sys.platform != "win32":
        log.warning("desktop alerts only work on Windows; alert not shown: %s - %s", title, body)
        return False
    env = {**os.environ, "STOCKMARKET_ALERT_TITLE": title[:100], "STOCKMARKET_ALERT_BODY": body[:300]}
    try:
        done = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", _TOAST_SCRIPT],
            env=env, capture_output=True, text=True, timeout=30,
        )
    except Exception as exc:
        log.warning("couldn't show the desktop alert: %s", exc)
        return False
    if done.returncode != 0:
        log.warning("couldn't show the desktop alert: %s", (done.stderr or done.stdout).strip()[:200])
        return False
    return True


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ok = send_notification("Stock market app: test alert", "If you can read this, nightly-job alerts will reach you.")
    print("Sent. Look for a notification at the bottom right." if ok else "Failed; see the message above.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
