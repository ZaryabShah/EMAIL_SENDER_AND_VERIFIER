#!/usr/bin/env python3
"""
Paralegal Email Verification System
Processes JSON files from grok_paralegal_search_results to verify paralegal/staff emails
Excludes attorney emails and provides summary reports per JSON file
Uses robust email verification from email_verifier.py with parallel processing
"""

import json
import os
import re
import time
import random
import string
import socket
import smtplib
import csv
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Tuple, Optional, Any
from collections import defaultdict
import dns.resolver
import dns.exception
import idna

# Configuration from email_verifier.py
DNS_TIMEOUT_SEC = 5.0
SMTP_TIMEOUT_SEC = 15.0
SMTP_PORT = 25
HELO_DOMAIN = "mail.example.com"
MAIL_FROM_SENDER = "noreply@example.com"
FAKE_LOCAL_PREFIX = "fakeemail"
USE_STARTTLS_IF_ADVERTISED = True
PER_MX_RETRY = 1
GLOBAL_BACKOFF_SEC = (0.5, 1.5)
MAX_WORKERS = 8  # Number of parallel workers

# Global SMTP status
SMTP_ENABLED = True

# Email validation regex from email_verifier.py
EMAIL_REGEX = re.compile(
    r"^(?P<local>[A-Za-z0-9!#$%&'*+/=?^_`{|}~.-]+)@(?P<domain>[A-Za-z0-9.-]+\.[A-Za-z]{2,})$"
)

# Cache for catch-all detection (per domain)
_catch_all_cache: Dict[str, Tuple[str, str]] = {}

def preflight_port25_check(test_hosts=("gmail-smtp-in.l.google.com","mx1.hotmail.com"), timeout=5) -> Tuple[bool, Optional[str]]:
    """Check if outbound TCP 25 is reachable"""
    for host in test_hosts:
        try:
            with socket.create_connection((host, SMTP_PORT), timeout=timeout):
                return True, host
        except Exception:
            pass
    return False, None

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

def idna_encode(domain: str) -> str:
    """Encode domain for international domain names"""
    try:
        return idna.encode(domain).decode("ascii")
    except Exception:
        return domain

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

def jitter_sleep(a=GLOBAL_BACKOFF_SEC[0], b=GLOBAL_BACKOFF_SEC[1]):
    """Add random delay to avoid being detected as automated"""
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

def random_fake_local() -> str:
    """Generate random fake local part for catch-all detection"""
    rand = "".join(random.choices(string.ascii_lowercase + string.digits, k=16))
    return FAKE_LOCAL_PREFIX + rand

def detect_catch_all(domain: str, mx_hosts: List[str]) -> Tuple[str, str]:
    """
    Probes a guaranteed-fake local part to see if the server accepts anything.
    Returns (catch_all, reason) where catch_all in {"yes","no","unknown"}.
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

def get_catch_all(domain: str, mx_hosts: List[str]) -> Tuple[str, str]:
    """Get catch-all status with caching per domain"""
    if not SMTP_ENABLED:
        return "unknown", "smtp disabled"
    if domain in _catch_all_cache:
        return _catch_all_cache[domain]
    result = detect_catch_all(domain, mx_hosts)
    _catch_all_cache[domain] = result
    return result

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

def verify_email(email_addr: str) -> Dict[str, Any]:
    """
    Main email verification function that returns comprehensive results
    """
    result = {
        'email': email_addr,
        'syntax_valid': False,
        'domain': '',
        'mx_hosts': [],
        'mx_primary': '',
        'catch_all_domain': 'unknown',
        'smtp_deliverable': 'unknown',
        'result': 'unknown',
        'reason': 'not processed'
    }
    
    # Syntax check
    syntax_ok, local, domain, syntax_reason = syntax_check(email_addr)
    if not syntax_ok:
        result.update({
            'syntax_valid': False,
            'result': 'undeliverable',
            'reason': f'syntax invalid: {syntax_reason}'
        })
        return result
    
    result['syntax_valid'] = True
    result['domain'] = domain
    
    # DNS MX lookup
    ascii_domain = idna_encode(domain)
    mx_hosts, dns_reason = mx_lookup(ascii_domain, DNS_TIMEOUT_SEC)
    result['mx_hosts'] = mx_hosts
    result['mx_primary'] = mx_hosts[0] if mx_hosts else ""
    
    if not mx_hosts:
        result.update({
            'result': 'undeliverable',
            'reason': f'no mx records: {dns_reason}'
        })
        return result
    
    # Catch-all detection (cached per domain)
    catch_all, catch_reason = get_catch_all(ascii_domain, mx_hosts)
    result['catch_all_domain'] = catch_all
    
    # SMTP deliverability probe
    smtp_status, smtp_reason, used_mx = verify_via_mx(email_addr, mx_hosts)
    result['smtp_deliverable'] = smtp_status
    
    # Final classification
    if smtp_status == "yes" and catch_all != "yes":
        result['result'] = "deliverable"
        result['reason'] = f"{smtp_reason}"
    elif smtp_status == "no":
        result['result'] = "undeliverable"
        result['reason'] = f"{smtp_reason}"
    else:
        # DNS-only mode or ambiguous SMTP outcome
        result['result'] = "unknown"
        result['reason'] = f"{smtp_reason or dns_reason}; catch_all={catch_all} ({catch_reason})"
    
    return result

def extract_paralegal_emails(json_file_path: str) -> List[Dict[str, Any]]:
    """
    Extract paralegal/staff emails from JSON file, excluding attorney emails
    Returns list of contact dictionaries with email and metadata
    """
    try:
        with open(json_file_path, 'r', encoding='utf-8', errors='ignore') as f:
            data = json.load(f)
        
        contacts = []
        
        # Skip attorney email
        attorney_email = None
        if 'attorney_info' in data and 'attorney_email' in data['attorney_info']:
            attorney_email = data['attorney_info']['attorney_email']
        
        # Extract paralegal emails from results.paralegals
        if 'results' in data and 'paralegals' in data['results']:
            for paralegal in data['results']['paralegals']:
                if 'email' in paralegal and paralegal['email']:
                    email = paralegal['email'].strip()
                    if email and email != attorney_email:  # Exclude attorney email
                        contact = {
                            'email': email,
                            'name': paralegal.get('name', ''),
                            'title': paralegal.get('title', ''),
                            'phone': paralegal.get('phone', ''),
                            'source_file': os.path.basename(json_file_path)
                        }
                        contacts.append(contact)
        
        return contacts
    
    except Exception as e:
        print(f"Error processing {json_file_path}: {e}")
        return []

def find_json_files(directory: str) -> List[str]:
    """Find all JSON files in the grok_paralegal_search_results directory"""
    json_files = []
    search_dir = Path(directory) / "grok_paralegal_search_results"
    
    if search_dir.exists():
        for json_file in search_dir.glob("*.json"):
            json_files.append(str(json_file))
    
    return sorted(json_files)

def process_json_file(json_file_path: str) -> Dict[str, Any]:
    """
    Process a single JSON file and verify all paralegal emails
    Returns summary with verification results
    """
    file_name = os.path.basename(json_file_path)
    print(f"Processing: {file_name}")
    
    # Extract paralegal contacts
    contacts = extract_paralegal_emails(json_file_path)
    
    if not contacts:
        return {
            'file': file_name,
            'total_contacts': 0,
            'verified_emails': [],
            'deliverable_count': 0,
            'undeliverable_count': 0,
            'unknown_count': 0,
            'error': 'No paralegal contacts found'
        }
    
    # Verify each email
    verified_results = []
    deliverable = 0
    undeliverable = 0
    unknown = 0
    
    for contact in contacts:
        email_result = verify_email(contact['email'])
        
        # Add contact metadata to result
        email_result.update({
            'contact_name': contact['name'],
            'contact_title': contact['title'],
            'contact_phone': contact['phone']
        })
        
        verified_results.append(email_result)
        
        # Count results
        if email_result['result'] == 'deliverable':
            deliverable += 1
        elif email_result['result'] == 'undeliverable':
            undeliverable += 1
        else:
            unknown += 1
    
    return {
        'file': file_name,
        'total_contacts': len(contacts),
        'verified_emails': verified_results,
        'deliverable_count': deliverable,
        'undeliverable_count': undeliverable,
        'unknown_count': unknown
    }

def save_detailed_results(all_results: List[Dict[str, Any]], output_file: str):
    """Save detailed verification results to CSV"""
    with open(output_file, 'w', newline='', encoding='utf-8') as csvfile:
        fieldnames = [
            'source_file', 'email', 'contact_name', 'contact_title', 'contact_phone',
            'syntax_valid', 'domain', 'mx_primary', 'catch_all_domain',
            'smtp_deliverable', 'result', 'reason'
        ]
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        
        for file_result in all_results:
            if 'error' in file_result:
                continue
            
            for email_result in file_result['verified_emails']:
                row = {
                    'source_file': file_result['file'],
                    'email': email_result['email'],
                    'contact_name': email_result.get('contact_name', ''),
                    'contact_title': email_result.get('contact_title', ''),
                    'contact_phone': email_result.get('contact_phone', ''),
                    'syntax_valid': email_result['syntax_valid'],
                    'domain': email_result['domain'],
                    'mx_primary': email_result['mx_primary'],
                    'catch_all_domain': email_result['catch_all_domain'],
                    'smtp_deliverable': email_result['smtp_deliverable'],
                    'result': email_result['result'],
                    'reason': email_result['reason']
                }
                writer.writerow(row)

def save_summary_results(all_results: List[Dict[str, Any]], output_file: str):
    """Save summary results per JSON file to CSV"""
    with open(output_file, 'w', newline='', encoding='utf-8') as csvfile:
        fieldnames = [
            'source_file', 'total_contacts', 'deliverable_count', 
            'undeliverable_count', 'unknown_count', 'deliverable_rate'
        ]
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        
        for file_result in all_results:
            if 'error' in file_result:
                row = {
                    'source_file': file_result['file'],
                    'total_contacts': 0,
                    'deliverable_count': 0,
                    'undeliverable_count': 0,
                    'unknown_count': 0,
                    'deliverable_rate': 0.0
                }
            else:
                total_definitive = file_result['deliverable_count'] + file_result['undeliverable_count']
                rate = (file_result['deliverable_count'] / total_definitive * 100) if total_definitive > 0 else 0.0
                
                row = {
                    'source_file': file_result['file'],
                    'total_contacts': file_result['total_contacts'],
                    'deliverable_count': file_result['deliverable_count'],
                    'undeliverable_count': file_result['undeliverable_count'],
                    'unknown_count': file_result['unknown_count'],
                    'deliverable_rate': round(rate, 1)
                }
            writer.writerow(row)

def main():
    """Main function to process all JSON files with parallel verification"""
    print("=== PARALEGAL EMAIL VERIFICATION SYSTEM ===")
    print(f"Max Workers: {MAX_WORKERS}")
    
    # Check SMTP connectivity
    global SMTP_ENABLED
    ok, tested_host = preflight_port25_check()
    if ok:
        SMTP_ENABLED = True
        print(f"Port 25 reachable (tested {tested_host}). SMTP RCPT checks ENABLED.")
    else:
        SMTP_ENABLED = False
        print("WARN: Outbound TCP 25 appears BLOCKED. Falling back to DNS-only mode.")
    print()
    
    # Find all JSON files
    current_dir = os.path.dirname(os.path.abspath(__file__))
    json_files = find_json_files(current_dir)
    
    if not json_files:
        print("No JSON files found in grok_paralegal_search_results directory!")
        return
    
    print(f"Found {len(json_files)} JSON files to process")
    print()
    
    # Process files with parallel workers
    all_results = []
    start_time = time.time()
    
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        # Submit all tasks
        future_to_file = {executor.submit(process_json_file, json_file): json_file 
                         for json_file in json_files}
        
        # Collect results as they complete
        for future in as_completed(future_to_file):
            json_file = future_to_file[future]
            try:
                result = future.result()
                all_results.append(result)
                
                # Print progress
                if 'error' not in result:
                    print(f"✓ {result['file']}: {result['deliverable_count']} deliverable, "
                          f"{result['undeliverable_count']} undeliverable, "
                          f"{result['unknown_count']} unknown")
                else:
                    print(f"✗ {result['file']}: {result['error']}")
                    
            except Exception as e:
                print(f"✗ {os.path.basename(json_file)}: Exception - {e}")
                all_results.append({
                    'file': os.path.basename(json_file),
                    'total_contacts': 0,
                    'deliverable_count': 0,
                    'undeliverable_count': 0,
                    'unknown_count': 0,
                    'error': str(e)
                })
    
    end_time = time.time()
    processing_time = end_time - start_time
    
    # Calculate totals
    total_contacts = sum(r.get('total_contacts', 0) for r in all_results if 'error' not in r)
    total_deliverable = sum(r.get('deliverable_count', 0) for r in all_results if 'error' not in r)
    total_undeliverable = sum(r.get('undeliverable_count', 0) for r in all_results if 'error' not in r)
    total_unknown = sum(r.get('unknown_count', 0) for r in all_results if 'error' not in r)
    
    # Save results
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    detailed_output = f"paralegal_verification_detailed_{timestamp}.csv"
    summary_output = f"paralegal_verification_summary_{timestamp}.csv"
    
    save_detailed_results(all_results, detailed_output)
    save_summary_results(all_results, summary_output)
    
    # Print final summary
    print("\n" + "="*60)
    print("FINAL SUMMARY")
    print("="*60)
    print(f"Processing time: {processing_time:.1f} seconds")
    print(f"JSON files processed: {len(all_results)}")
    print(f"Total paralegal contacts: {total_contacts}")
    print(f"Deliverable emails: {total_deliverable}")
    print(f"Undeliverable emails: {total_undeliverable}")
    print(f"Unknown status emails: {total_unknown}")
    
    if total_deliverable + total_undeliverable > 0:
        rate = total_deliverable / (total_deliverable + total_undeliverable) * 100
        print(f"Deliverability rate (excluding unknowns): {rate:.1f}%")
    
    print(f"\nDetailed results: {detailed_output}")
    print(f"Summary results: {summary_output}")
    
    if not SMTP_ENABLED:
        print("\nNOTE: SMTP was disabled due to blocked port 25.")
        print("Only syntax + DNS checks were performed.")
    
    print("\nVerification complete!")

if __name__ == "__main__":
    random.seed()  # Initialize random seed for jitter and fake emails
    main()
