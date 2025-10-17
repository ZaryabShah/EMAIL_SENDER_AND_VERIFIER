#!/usr/bin/env python3
"""
Standalone Email Verification and Sending Pipeline
Command-line interface for email verification and bulk sending
"""

import argparse
import sys
import os
from standalone_email_verifier import EmailVerifier
from standalone_email_sender import EmailSender
from standalone_email_manager import EmailListManager


def main():
    parser = argparse.ArgumentParser(
        description="Email Verification and Sending Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Verify emails from a file
  python email_pipeline.py verify --input emails.txt --output-valid valid.txt --output-invalid invalid.txt
  
  # Send emails from a file
  python email_pipeline.py send --input valid_emails.txt --template basic_outreach --max-emails 10
  
  # Complete pipeline: verify then send
  python email_pipeline.py pipeline --input raw_emails.txt --template basic_outreach --max-emails 50
  
  # Add emails to managed queue
  python email_pipeline.py queue add --input emails.txt
  
  # Process emails from managed queue
  python email_pipeline.py queue process --template basic_outreach --max-emails 20
  
  # Show queue statistics
  python email_pipeline.py queue stats
        """
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # Verify command
    verify_parser = subparsers.add_parser('verify', help='Verify email addresses')
    verify_parser.add_argument('--input', '-i', required=True, help='Input file with email addresses')
    verify_parser.add_argument('--output-valid', '-ov', help='Output file for valid emails')
    verify_parser.add_argument('--output-invalid', '-oi', help='Output file for invalid emails')
    verify_parser.add_argument('--quiet', '-q', action='store_true', help='Suppress progress output')
    
    # Send command
    send_parser = subparsers.add_parser('send', help='Send emails to recipients')
    send_parser.add_argument('--input', '-i', required=True, help='Input file with email addresses')
    send_parser.add_argument('--config', '-c', default='email_config.json', help='Email configuration file')
    send_parser.add_argument('--template', '-t', help='Template name to use')
    send_parser.add_argument('--subject', '-s', help='Email subject line')
    send_parser.add_argument('--delay-min', default=5, type=int, help='Minimum delay between emails (seconds)')
    send_parser.add_argument('--delay-max', default=15, type=int, help='Maximum delay between emails (seconds)')
    send_parser.add_argument('--max-emails', '-m', type=int, help='Maximum number of emails to send')
    send_parser.add_argument('--account-index', type=int, help='Specific account index to use')
    
    # Pipeline command (verify + send)
    pipeline_parser = subparsers.add_parser('pipeline', help='Complete pipeline: verify then send')
    pipeline_parser.add_argument('--input', '-i', required=True, help='Input file with email addresses')
    pipeline_parser.add_argument('--config', '-c', default='email_config.json', help='Email configuration file')
    pipeline_parser.add_argument('--template', '-t', help='Template name to use')
    pipeline_parser.add_argument('--subject', '-s', help='Email subject line')
    pipeline_parser.add_argument('--delay-min', default=5, type=int, help='Minimum delay between emails (seconds)')
    pipeline_parser.add_argument('--delay-max', default=15, type=int, help='Maximum delay between emails (seconds)')
    pipeline_parser.add_argument('--max-emails', '-m', type=int, help='Maximum number of emails to send')
    pipeline_parser.add_argument('--keep-invalid', action='store_true', help='Keep invalid emails file')
    pipeline_parser.add_argument('--verify-only', action='store_true', help='Only verify, do not send')
    
    # Queue management commands
    queue_parser = subparsers.add_parser('queue', help='Manage email queue')
    queue_subparsers = queue_parser.add_subparsers(dest='queue_action', help='Queue actions')
    
    # Queue add
    queue_add = queue_subparsers.add_parser('add', help='Add emails to queue')
    queue_add.add_argument('--input', '-i', required=True, help='Input file with email addresses')
    queue_add.add_argument('--source', help='Source description for logging')
    
    # Queue process
    queue_process = queue_subparsers.add_parser('process', help='Process emails from queue')
    queue_process.add_argument('--config', '-c', default='email_config.json', help='Email configuration file')
    queue_process.add_argument('--template', '-t', help='Template name to use')
    queue_process.add_argument('--subject', '-s', help='Email subject line')
    queue_process.add_argument('--delay-min', default=5, type=int, help='Minimum delay between emails (seconds)')
    queue_process.add_argument('--delay-max', default=15, type=int, help='Maximum delay between emails (seconds)')
    queue_process.add_argument('--max-emails', '-m', type=int, help='Maximum number of emails to process')
    queue_process.add_argument('--verify-first', action='store_true', help='Verify emails before sending')
    
    # Queue stats
    queue_subparsers.add_parser('stats', help='Show queue statistics')
    
    # Queue cleanup
    queue_cleanup = queue_subparsers.add_parser('cleanup', help='Remove duplicates from queue')
    
    # List templates and accounts
    list_parser = subparsers.add_parser('list', help='List templates and accounts')
    list_parser.add_argument('--config', '-c', default='email_config.json', help='Email configuration file')
    list_parser.add_argument('type', choices=['templates', 'accounts', 'all'], help='What to list')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    # Execute commands
    if args.command == 'verify':
        cmd_verify(args)
    elif args.command == 'send':
        cmd_send(args)
    elif args.command == 'pipeline':
        cmd_pipeline(args)
    elif args.command == 'queue':
        cmd_queue(args)
    elif args.command == 'list':
        cmd_list(args)


def cmd_verify(args):
    """Handle verify command"""
    print("Starting email verification...")
    
    verifier = EmailVerifier()
    stats = verifier.verify_from_file(
        args.input,
        args.output_valid,
        args.output_invalid
    )
    
    if stats:
        print(f"\\nVerification completed successfully!")
    else:
        print("Verification failed!")
        sys.exit(1)


def cmd_send(args):
    """Handle send command"""
    print("Starting email sending...")
    
    sender = EmailSender(args.config)
    stats = sender.send_from_file(
        args.input,
        subject=args.subject,
        template_name=args.template,
        delay_range=(args.delay_min, args.delay_max),
        max_emails=args.max_emails
    )
    
    if stats:
        print(f"\\nEmail sending completed!")
    else:
        print("Email sending failed!")
        sys.exit(1)


def cmd_pipeline(args):
    """Handle pipeline command (verify + send)"""
    print("Starting complete email pipeline...")
    
    # Step 1: Verify emails
    print("\\n=== Step 1: Email Verification ===")
    verifier = EmailVerifier()
    
    # Create temporary files for verified emails
    valid_emails_file = f"{args.input}.valid"
    invalid_emails_file = f"{args.input}.invalid"
    
    verify_stats = verifier.verify_from_file(
        args.input,
        valid_emails_file,
        invalid_emails_file if args.keep_invalid else None
    )
    
    if not verify_stats or verify_stats['valid'] == 0:
        print("No valid emails found. Stopping pipeline.")
        return
    
    if args.verify_only:
        print("Verification complete. Stopping as requested.")
        return
    
    # Step 2: Send emails to verified addresses
    print("\\n=== Step 2: Email Sending ===")
    sender = EmailSender(args.config)
    send_stats = sender.send_from_file(
        valid_emails_file,
        subject=args.subject,
        template_name=args.template,
        delay_range=(args.delay_min, args.delay_max),
        max_emails=args.max_emails
    )
    
    # Cleanup temporary files
    if os.path.exists(valid_emails_file):
        os.remove(valid_emails_file)
    if not args.keep_invalid and os.path.exists(invalid_emails_file):
        os.remove(invalid_emails_file)
    
    print("\\n=== Pipeline Complete ===")
    print(f"Total emails processed: {verify_stats['total']}")
    print(f"Valid emails found: {verify_stats['valid']}")
    print(f"Emails sent successfully: {send_stats.get('successful', 0)}")
    print(f"Overall success rate: {(send_stats.get('successful', 0) / verify_stats['total'] * 100):.2f}%")


def cmd_queue(args):
    """Handle queue management commands"""
    manager = EmailListManager()
    
    if args.queue_action == 'add':
        print(f"Adding emails from {args.input} to queue...")
        added = manager.add_emails_from_file(args.input, args.source)
        print(f"Added {added} emails to the queue")
        manager.print_statistics()
        
    elif args.queue_action == 'process':
        print("Processing emails from queue...")
        
        sender = EmailSender(args.config)
        processed = 0
        max_emails = args.max_emails or float('inf')
        
        while processed < max_emails:
            # Get next email from queue
            email = manager.get_next_email()
            if not email:
                print("No more emails in queue")
                break
            
            # Verify email if requested
            if args.verify_first:
                verifier = EmailVerifier()
                if not verifier.verify_email_dns_smtp(email):
                    print(f"Skipping invalid email: {email}")
                    manager.mark_email_failed(email, "Email verification failed")
                    continue
            
            # Send email
            print(f"Sending email {processed + 1} to: {email}")
            success, sender_email, error = sender.send_single_email(
                email,
                subject=args.subject,
                template_name=args.template
            )
            
            if success:
                manager.mark_email_sent(email, sender_email)
                print(f"✓ Email sent successfully from {sender_email}")
            else:
                manager.mark_email_failed(email, error, sender_email)
                print(f"✗ Failed to send email: {error}")
            
            processed += 1
            
            # Add delay between emails
            if processed < max_emails and manager.get_statistics()['queue_count'] > 0:
                import random
                from time import sleep
                delay = random.randint(args.delay_min, args.delay_max)
                print(f"Waiting {delay} seconds before next email...")
                sleep(delay)
        
        print(f"\\nProcessed {processed} emails from queue")
        manager.print_statistics()
        
    elif args.queue_action == 'stats':
        manager.print_statistics()
        
    elif args.queue_action == 'cleanup':
        removed = manager.remove_duplicates_from_queue()
        print(f"Removed {removed} duplicate emails from queue")
        manager.print_statistics()


def cmd_list(args):
    """Handle list command"""
    sender = EmailSender(args.config)
    
    if args.type in ['templates', 'all']:
        print("\\n=== Email Templates ===")
        sender.list_templates()
    
    if args.type in ['accounts', 'all']:
        print("\\n=== Email Accounts ===")
        sender.list_accounts()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\\n\\nOperation cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\\nError: {e}")
        sys.exit(1)
