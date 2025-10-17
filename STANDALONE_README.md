# Standalone Email Verification and Sending Pipeline

A lightweight, independent email verification and bulk sending system extracted from the main Gmail Finder and Sender project.

## Features

- **Email Verification**: DNS and SMTP validation of email addresses
- **Bulk Email Sending**: Send personalized emails with template randomization
- **Account Rotation**: Automatically rotate between multiple sender accounts
- **Queue Management**: Manage email lists, track sent emails, handle duplicates
- **Template System**: Randomized email templates with multiple variations
- **CLI Interface**: Complete command-line interface for all operations
- **Logging**: Track all operations with timestamps
- **Statistics**: Monitor success rates and queue status

## Quick Start

### 1. Install Dependencies
```bash
pip install -r standalone_requirements.txt
```

### 2. Configure Email Accounts
Edit `email_config.json` and add your email accounts:
```json
{
    "email_accounts": [
        {
            "sender_email": "your-email@gmail.com",
            "sender_password": "your-app-password",
            "sender_name": "Your Name",
            "smtp_server": "smtp.gmail.com",
            "smtp_port": 587,
            "use_tls": true
        }
    ]
}
```

### 3. Basic Usage

**Verify email addresses:**
```bash
python email_pipeline.py verify --input emails.txt --output-valid valid.txt --output-invalid invalid.txt
```

**Send emails:**
```bash
python email_pipeline.py send --input valid_emails.txt --template ai_automation --max-emails 10
```

**Complete pipeline (verify + send):**
```bash
python email_pipeline.py pipeline --input raw_emails.txt --template ai_automation --max-emails 50
```

## File Structure

```
standalone_email_verifier.py    # Email verification module
standalone_email_sender.py      # Email sending module  
standalone_email_manager.py     # Email list management
email_pipeline.py              # CLI interface
email_config.json              # Configuration file
standalone_requirements.txt    # Dependencies
```

## Module Usage

### Email Verifier
```python
from standalone_email_verifier import EmailVerifier

verifier = EmailVerifier()

# Verify single email
is_valid = verifier.verify_email_dns_smtp("test@example.com")

# Verify from file
stats = verifier.verify_from_file("emails.txt", "valid.txt", "invalid.txt")
```

### Email Sender
```python
from standalone_email_sender import EmailSender

sender = EmailSender("email_config.json")

# Send single email
success, sender_email, error = sender.send_single_email(
    "recipient@example.com", 
    template_name="ai_automation"
)

# Send bulk emails
stats = sender.send_from_file("emails.txt", template_name="ai_automation")
```

### Email Manager
```python
from standalone_email_manager import EmailListManager

manager = EmailListManager()

# Add emails to queue
manager.add_emails_from_file("new_emails.txt")

# Process queue
email = manager.get_next_email()
manager.mark_email_sent(email, "sender@example.com")

# Get statistics
manager.print_statistics()
```

## CLI Commands

### Verification
```bash
# Basic verification
python email_pipeline.py verify -i emails.txt -ov valid.txt -oi invalid.txt

# Quiet mode
python email_pipeline.py verify -i emails.txt -ov valid.txt -q
```

### Sending
```bash
# Send with specific template
python email_pipeline.py send -i emails.txt -t ai_automation -m 20

# Custom delays and subject
python email_pipeline.py send -i emails.txt -t basic_outreach -s "Custom Subject" --delay-min 10 --delay-max 30
```

### Queue Management
```bash
# Add emails to managed queue
python email_pipeline.py queue add -i emails.txt --source "lead_generation"

# Process emails from queue
python email_pipeline.py queue process -t ai_automation -m 25 --verify-first

# Show queue statistics
python email_pipeline.py queue stats

# Remove duplicates
python email_pipeline.py queue cleanup
```

### Utilities
```bash
# List available templates and accounts
python email_pipeline.py list all

# List only templates
python email_pipeline.py list templates
```

## Email Templates

Templates support randomization using `{option1|option2|option3}` syntax:

```
{Hi|Hey|Hello},

{This is a test|Hope you're well|Quick message}.

{Best regards|Cheers|Talk soon},
Your Name
```

## Configuration

### Email Account Setup
- **Gmail**: Use App Passwords (not regular password)
- **SMTP Settings**: Adjust server and port as needed
- **TLS/SSL**: Configure based on provider requirements

### Template Configuration
- Add templates to `email_config.json`
- Use `{option1|option2}` for randomization
- Include line breaks with `\n`

## Data Management

The system creates an `email_data/` directory with:
- `email_queue.txt` - Emails waiting to be sent
- `sent_emails.txt` - Successfully sent emails with timestamps
- `failed_emails.txt` - Failed emails with error reasons
- `verified_emails.txt` - Verified valid emails
- `invalid_emails.txt` - Invalid email addresses
- `email_log.txt` - Operation log with timestamps

## Best Practices

1. **Email Verification**: Always verify emails before sending to reduce bounce rates
2. **Rate Limiting**: Use appropriate delays between emails (5-15 seconds recommended)
3. **Account Rotation**: Use multiple sender accounts to distribute load
4. **Template Variation**: Use randomized templates to avoid spam filters
5. **Monitoring**: Check logs and statistics regularly
6. **Compliance**: Ensure you have permission to email recipients

## Error Handling

The system handles:
- Invalid email formats
- DNS resolution failures
- SMTP connection errors
- Authentication failures
- Rate limiting
- Duplicate detection

## Limitations

- Requires valid SMTP credentials
- Subject to email provider rate limits
- DNS/SMTP verification may not be 100% accurate
- Some email providers block verification attempts

## Legal Notice

This tool is for legitimate business outreach only. Always:
- Obtain proper consent before sending emails
- Follow anti-spam laws (CAN-SPAM, GDPR, etc.)
- Respect opt-out requests
- Use appropriate content and frequency
