#!/usr/bin/env python3
"""
Email Deliverability Verifier
- Syntax + IDNA + MX (always)
- SMTP RCPT + Catch-all (only if outbound TCP 25 is reachable)

Input : emails_to_verify.csv  (must contain a column named 'email')
Output: email_verification_results.csv

Notes:
- No message content is ever sent; we stop at RCPT TO.
- If port 25 is blocked, the script falls back to DNS-only mode and marks SMTP fields as "unknown".
"""

import csv
import re
import time
import socket
import random
import string
from typing import Optional, Tuple, List, Dict

# --- Third-party deps (auto-install if missing) ---
try:
    import idna
    import dns.resolver
except ImportError:
    print("Installing required packages...")
    import subprocess, sys
    subprocess.check_call([sys.executable, "-m", "pip", "install", "dnspython", "idna"])
    import idna
    import dns.resolver

import smtplib

# ---------------- Configuration ----------------
DNS_TIMEOUT_SEC = 5.0
SMTP_TIMEOUT_SEC = 15.0
SMTP_PORT = 25
PER_MX_RETRY = 1                 # retries per MX on transient/unknown codes
GLOBAL_BACKOFF_SEC = (0.15, 0.5) # jitter between network ops
USE_STARTTLS_IF_ADVERTISED = True
HELO_DOMAIN = "example.com"      # ideally your domain
MAIL_FROM_SENDER = "validator@example.com"  # benign sender (not <>)
FAKE_LOCAL_PREFIX = "this-address-should-not-exist-"  # for catch-all probe
INPUT_CSV = "emails_to_verify.csv"
OUTPUT_CSV = "email_verification_results.csv"

# Will be auto-detected at runtime
SMTP_ENABLED = True

# -------------- Preflight: is outbound TCP 25 reachable? --------------
def preflight_port25_check(test_hosts=("gmail-smtp-in.l.google.com","mx1.hotmail.com"), timeout=5) -> Tuple[bool, Optional[str]]:
    for host in test_hosts:
        try:
            with socket.create_connection((host, SMTP_PORT), timeout=timeout):
                return True, host
        except Exception:
            pass
    return False, None

# -------------- Syntax Validation --------------
EMAIL_REGEX = re.compile(
    r"^(?P<local>[A-Za-z0-9!#$%&'*+/=?^_`{|}~.-]+)@(?P<domain>[A-Za-z0-9.-]+\.[A-Za-z]{2,})$"
)

def syntax_check(addr: str) -> Tuple[bool, Optional[str], Optional[str], str]:
    """Check email syntax validity with simple local-part dot rules."""
    m = EMAIL_REGEX.match((addr or "").strip())
    if not m:
        return False, None, None, "regex failed"
    local = m.group("local")
    domain = m.group("domain")
    if local.startswith(".") or local.endswith(".") or ".." in local:
        return False, None, None, "local-part dots invalid"
    return True, local, domain, "ok"

# -------------- IDNA encode domains --------------
def idna_encode(domain: str) -> str:
    try:
        return idna.encode(domain).decode("ascii")
    except Exception:
        return domain  # best effort

# -------------- DNS MX lookup --------------
def mx_lookup(domain: str, timeout: float = DNS_TIMEOUT_SEC) -> Tuple[List[str], str]:
    """
    Returns (mx_hosts_sorted, reason). If no MX, tries A record and returns [domain].
    """
    resolver = dns.resolver.Resolver()
    resolver.lifetime = timeout
    resolver.timeout = timeout
    try:
        answers = resolver.resolve(domain, "MX")
        mx_records = sorted(
            [(r.preference, str(r.exchange).rstrip(".")) for r in answers],
            key=lambda x: x[0],
        )
        mx_hosts = [mx for _, mx in mx_records]
        return mx_hosts, "found MX"
    except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer):
        # Try A record fallback
        try:
            resolver.resolve(domain, "A")
            return [domain], "no MX; using A record"
        except Exception:
            return [], "no MX and no A"
    except dns.exception.Timeout:
        return [], "dns timeout"
    except Exception as e:
        return [], f"dns error: {e!r}"

# -------------- SMTP utilities --------------
def jitter_sleep(a=GLOBAL_BACKOFF_SEC[0], b=GLOBAL_BACKOFF_SEC[1]):
    time.sleep(random.uniform(a, b))

def smtp_rcpt_check(
    recipient: str,
    mx_host: str,
    timeout: float = SMTP_TIMEOUT_SEC,
    use_starttls: bool = True,
) -> Tuple[str, str]:
    """
    Try SMTP dialog with given MX host and ask RCPT TO for recipient.
    Returns (status, reason) where status in {"yes", "no", "unknown"}.
    """
    try:
        with smtplib.SMTP(mx_host, SMTP_PORT, timeout=timeout) as s:
            code, _ = s.ehlo()
            if 200 <= code < 300:
                if use_starttls and s.has_extn("starttls"):
                    try:
                        s.starttls()
                        s.ehlo()
                    except Exception:
                        # Not fatal; continue without TLS
                        pass
            else:
                # HELO fallback
                s.helo(HELO_DOMAIN)

            # Some servers reject null MAIL FROM; use benign mailbox
            s.mail(MAIL_FROM_SENDER)

            code, msg = s.rcpt(recipient)
            if code in (250, 251):          # Accepted / will forward
                return "yes", f"rcpt accepted ({code}) {msg!r}"
            if code in (550, 551, 553, 554):  # Not found / not allowed
                return "no", f"rcpt rejected ({code}) {msg!r}"
            if code in (450, 451, 452):     # Temporary failures
                return "unknown", f"temporary failure ({code}) {msg!r}"

            return "unknown", f"rcpt response ({code}) {msg!r}"

    except smtplib.SMTPServerDisconnected as e:
        return "unknown", f"smtp disconnected: {e!r}"
    except (smtplib.SMTPConnectError, smtplib.SMTPHeloError) as e:
        return "unknown", f"smtp connect/helo error: {e!r}"
    except smtplib.SMTPRecipientsRefused as e:
        # Dict of refused recipients with (code, response)
        try:
            code, resp = list(e.recipients.values())[0]
            if code in (550, 551, 553, 554):
                return "no", f"rcpt refused ({code}) {resp!r}"
            elif code in (450, 451, 452):
                return "unknown", f"temporary refusal ({code}) {resp!r}"
        except Exception:
            pass
        return "unknown", f"recipients refused: {e!r}"
    # Python commonly raises socket.timeout or built-in TimeoutError here
    except (socket.timeout, TimeoutError, OSError):
        return "unknown", "smtp timeout"
    except Exception as e:
        return "unknown", f"smtp error: {e!r}"

# -------------- Catch-all detection (per domain) --------------
def random_fake_local() -> str:
    rand = "".join(random.choices(string.ascii_lowercase + string.digits, k=16))
    return FAKE_LOCAL_PREFIX + rand

def detect_catch_all(domain: str, mx_hosts: List[str]) -> Tuple[str, str]:
    """
    Probes a guaranteed-fake local part to see if the server accepts anything.
    Returns (catch_all, reason) where catch_all in {"yes","no","unknown"}.
    Tries MX hosts until a definitive 'yes' or 'no' or all unknown.
    """
    if not mx_hosts:
        return "unknown", "no mx"

    fake_address = f"{random_fake_local()}@{domain}"
    last_reason = "unknown"
    for mx in mx_hosts:
        for _ in range(PER_MX_RETRY + 1):
            jitter_sleep()
            status, reason = smtp_rcpt_check(fake_address, mx, use_starttls=USE_STARTTLS_IF_ADVERTISED)
            last_reason = reason
            if status in ("yes", "no"):
                return ("yes" if status == "yes" else "no"), f"{reason} via {mx}"
    return "unknown", last_reason

# -------------- Domain-level cache for catch-all --------------
_catch_all_cache: Dict[str, Tuple[str, str]] = {}

def get_catch_all(domain: str, mx_hosts: List[str]) -> Tuple[str, str]:
    if not SMTP_ENABLED:
        return "unknown", "smtp disabled"
    if domain in _catch_all_cache:
        return _catch_all_cache[domain]
    result = detect_catch_all(domain, mx_hosts)
    _catch_all_cache[domain] = result
    return result

# -------------- Per-email verification --------------
def verify_via_mx(recipient: str, mx_hosts: List[str]) -> Tuple[str, str, str]:
    """
    Probes each MX until definitive yes/no; returns (smtp_deliverable, reason, mx_used)
    smtp_deliverable in {"yes","no","unknown"}
    """
    if not SMTP_ENABLED:
        return "unknown", "smtp disabled", ""
    if not mx_hosts:
        return "unknown", "no mx", ""
    last_reason = "unknown"
    used = ""
    for mx in mx_hosts:
        for _ in range(PER_MX_RETRY + 1):
            jitter_sleep()
            status, reason = smtp_rcpt_check(recipient, mx, use_starttls=USE_STARTTLS_IF_ADVERTISED)
            last_reason = reason
            used = mx
            if status in ("yes", "no"):
                return status, reason, mx
    return "unknown", last_reason, used

# -------------- Main I/O --------------
def main():
    print("=== EMAIL DELIVERABILITY VERIFIER ===")
    print(f"Input : {INPUT_CSV}")
    print(f"Output: {OUTPUT_CSV}")
    print("Note : No messages are sent. We stop at RCPT TO.\n")

    # Preflight port 25 reachability
    global SMTP_ENABLED
    ok, tested_host = preflight_port25_check()
    if ok:
        SMTP_ENABLED = True
        print(f"Port 25 reachable (tested {tested_host}). SMTP RCPT checks ENABLED.\n")
    else:
        SMTP_ENABLED = False
        print("WARN: Outbound TCP 25 appears BLOCKED. Falling back to DNS-only mode (no RCPT checks, no catch-all).\n")

    # Read input CSV
    try:
        with open(INPUT_CSV, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            email_col = None
            for col in reader.fieldnames or []:
                if col.lower() == "email":
                    email_col = col
                    break
            if not email_col:
                raise ValueError("Input CSV must have a column named 'email'")
            emails = [row[email_col].strip() for row in reader if row.get(email_col)]
    except Exception as e:
        print(f"Error reading input CSV: {e}")
        return

    print(f"Found {len(emails)} emails to verify.")

    # Process
    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as out_f:
        writer = csv.writer(out_f)
        writer.writerow([
            "email",
            "syntax_valid",
            "domain",
            "mx_hosts",
            "mx_primary",
            "catch_all_domain",
            "smtp_deliverable",
            "result",
            "reason",
        ])

        deliverable = 0
        undeliverable = 0
        unknowns = 0

        for idx, addr in enumerate(emails, 1):
            if idx % 25 == 0:
                print(f"  Processed {idx}/{len(emails)} ...")

            syntax_ok, local, domain, _ = syntax_check(addr)
            if not syntax_ok:
                writer.writerow([addr, False, "", "", "", "unknown", "no", "undeliverable", "syntax invalid"])
                undeliverable += 1
                continue

            ascii_domain = idna_encode(domain)
            mx_hosts, dns_reason = mx_lookup(ascii_domain, DNS_TIMEOUT_SEC)
            primary = mx_hosts[0] if mx_hosts else ""

            # Catch-all (cached per domain) — skipped when SMTP disabled
            catch_all, catch_reason = get_catch_all(ascii_domain, mx_hosts)

            # Deliverability probe — skipped when SMTP disabled
            smtp_status, smtp_reason, used_mx = verify_via_mx(addr, mx_hosts)

            # Final classification
            if smtp_status == "yes" and catch_all != "yes":
                result = "deliverable"
                deliverable += 1
                reason = f"{smtp_reason}"
            elif smtp_status == "no":
                result = "undeliverable"
                undeliverable += 1
                reason = f"{smtp_reason}"
            else:
                # DNS-only mode or ambiguous SMTP outcome
                result = "unknown"
                unknowns += 1
                # Prefer SMTP reason; otherwise DNS reason; include catch-all context
                reason = f"{smtp_reason or dns_reason}; catch_all={catch_all} ({catch_reason})"

            writer.writerow([
                addr,
                True,
                ascii_domain,
                ";".join(mx_hosts),
                primary,
                catch_all,
                smtp_status,
                result,
                reason,
            ])

    print("\n=== COMPLETE ===")
    print(f"Results written to: {OUTPUT_CSV}")
    print(f"Deliverable : {deliverable}")
    print(f"Undeliverable: {undeliverable}")
    print(f"Unknown     : {unknowns}")
    denom = (deliverable + undeliverable)
    rate = (deliverable / denom * 100) if denom else 0.0
    print(f"Deliverability rate (excl. unknowns): {rate:.1f}%")
    print("\nNotes:")
    if not SMTP_ENABLED:
        print("- SMTP disabled due to blocked port 25; only syntax + DNS were checked.")
    print("- 'unknown' can mean temp failures, greylisting, anti-harvesting behavior, or catch-all.")
    print("- 'catch_all=yes' means the domain accepts any local part at RCPT, so existence can't be proven.")

if __name__ == "__main__":
    random.seed()  # for jitter + fake local generation
    main()
