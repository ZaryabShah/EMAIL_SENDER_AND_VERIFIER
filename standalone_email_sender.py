import smtplib
import ssl
import random
import re
import json
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import List, Dict, Tuple
from time import sleep


class EmailSender:
    """
    Standalone email sending system with template randomization and account rotation
    """
    
    def __init__(self, config_file: str = "email_config.json"):
        """
        Initialize EmailSender with configuration
        
        Args:
            config_file (str): Path to JSON config file containing email accounts and templates
        """
        self.config_file = config_file
        self.email_accounts = []
        self.email_templates = []
        self.subject_lines = []
        self.current_account_index = 0
        
        # Default subject lines if none provided
        self.default_subjects = [
            "AI?",
            "can we just fix this outreach hassle already??",
            "what iF OutREach WAsn't Your proBlem anyMOre?!",
            "can I fix this outreach problem with AI?!",
            "you've been doing outreach wrong…",
            "tryna crack this outreach code—thoughts...",
            "is this the end of our outreach headache (thanks to AI)?",
            "outreach struggles? Maybe AI's got it.",
            "i don't want to believe this lead machine…"
        ]
        
        self.load_configuration()
    
    def load_configuration(self):
        """Load email accounts and templates from config file"""
        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
                
            self.email_accounts = config.get('email_accounts', [])
            self.email_templates = config.get('email_templates', [])
            self.subject_lines = config.get('subject_lines', self.default_subjects)
            
            if not self.email_accounts:
                print("Warning: No email accounts found in config")
            if not self.email_templates:
                print("Warning: No email templates found in config")
                
        except FileNotFoundError:
            print(f"Config file {self.config_file} not found. Creating default config...")
            self.create_default_config()
        except json.JSONDecodeError as e:
            print(f"Error parsing config file: {e}")
            
    def create_default_config(self):
        """Create a default configuration file"""
        default_config = {
            "email_accounts": [
                {
                    "sender_email": "your-email@gmail.com",
                    "sender_password": "your-app-password",
                    "smtp_server": "smtp.gmail.com",
                    "smtp_port": 587,
                    "use_tls": True
                }
            ],
            "email_templates": [
                {
                    "name": "basic_outreach",
                    "content": "Hi,\\n\\nI hope this email finds you well.\\n\\n{This is a test email|Hope you're having a great day|Quick message for you}.\\n\\nBest regards,\\nYour Name"
                }
            ],
            "subject_lines": self.default_subjects
        }
        
        with open(self.config_file, 'w', encoding='utf-8') as f:
            json.dump(default_config, f, indent=4)
        
        print(f"Default config created at {self.config_file}")
        print("Please update the config file with your email credentials and templates")
    
    def randomize_template(self, template: str) -> str:
        """
        Randomize template by selecting random options from {option1|option2|option3} blocks
        
        Args:
            template (str): Template with randomization options in curly braces
            
        Returns:
            str: Randomized template
        """
        pattern = r"\\{(.*?)\\}"
        
        def select_random(match):
            options = match.group(1).split('|')
            return random.choice(options)
        
        return re.sub(pattern, select_random, template)
    
    def get_random_subject(self) -> str:
        """Get a random subject line"""
        return random.choice(self.subject_lines)
    
    def get_next_account(self) -> Dict:
        """Get next email account using round-robin rotation"""
        if not self.email_accounts:
            raise ValueError("No email accounts configured")
        
        account = self.email_accounts[self.current_account_index]
        self.current_account_index = (self.current_account_index + 1) % len(self.email_accounts)
        return account
    
    def send_single_email(self, recipient_email: str, subject: str = None, template_name: str = None, custom_template: str = None, account_index: int = None) -> Tuple[bool, str, str]:
        """
        Send a single email
        
        Args:
            recipient_email (str): Recipient's email address
            subject (str): Email subject (optional, will use random if not provided)
            template_name (str): Name of template to use from config
            custom_template (str): Custom template content
            account_index (int): Specific account index to use (optional)
            
        Returns:
            Tuple[bool, str, str]: (success, sender_email, error_message)
        """
        try:
            # Get email account
            if account_index is not None and 0 <= account_index < len(self.email_accounts):
                account = self.email_accounts[account_index]
            else:
                account = self.get_next_account()
            
            # Get template content
            if custom_template:
                template_content = custom_template
            elif template_name:
                template_content = next(
                    (t['content'] for t in self.email_templates if t['name'] == template_name),
                    None
                )
                if not template_content:
                    return False, account['sender_email'], f"Template '{template_name}' not found"
            else:
                if self.email_templates:
                    template_content = random.choice(self.email_templates)['content']
                else:
                    return False, account['sender_email'], "No templates available"
            
            # Randomize template
            email_content = self.randomize_template(template_content)
            
            # Get subject
            if not subject:
                subject = self.get_random_subject()
            
            # Create email message
            msg = MIMEMultipart()
            msg['From'] = f"{account.get('sender_name', 'Sender')} <{account['sender_email']}>"
            msg['To'] = recipient_email
            msg['Subject'] = subject
            
            # Determine if content is HTML
            if '<html>' in email_content.lower() or '<br>' in email_content.lower():
                msg.attach(MIMEText(email_content, 'html'))
            else:
                msg.attach(MIMEText(email_content, 'plain'))
            
            # Send email
            smtp_server = account.get('smtp_server', 'smtp.gmail.com')
            smtp_port = account.get('smtp_port', 587)
            use_tls = account.get('use_tls', True)
            
            if use_tls:
                context = ssl.create_default_context()
                with smtplib.SMTP(smtp_server, smtp_port) as server:
                    server.starttls(context=context)
                    server.login(account['sender_email'], account['sender_password'])
                    server.send_message(msg)
            else:
                context = ssl.create_default_context()
                with smtplib.SMTP_SSL(smtp_server, smtp_port, context=context) as server:
                    server.login(account['sender_email'], account['sender_password'])
                    server.send_message(msg)
            
            return True, account['sender_email'], "Success"
            
        except Exception as e:
            return False, account.get('sender_email', 'Unknown'), str(e)
    
    def send_bulk_emails(self, recipient_list: List[str], subject: str = None, template_name: str = None, delay_range: Tuple[int, int] = (5, 15), max_emails: int = None) -> Dict:
        """
        Send emails to multiple recipients with delays and account rotation
        
        Args:
            recipient_list (List[str]): List of recipient email addresses
            subject (str): Email subject (optional)
            template_name (str): Template name to use
            delay_range (Tuple[int, int]): Min and max delay between emails in seconds
            max_emails (int): Maximum number of emails to send
            
        Returns:
            Dict: Statistics about the sending process
        """
        stats = {
            'total_attempted': 0,
            'successful': 0,
            'failed': 0,
            'successful_emails': [],
            'failed_emails': [],
            'errors': []
        }
        
        # Limit number of emails if specified
        if max_emails:
            recipient_list = recipient_list[:max_emails]
        
        print(f"Starting bulk email send to {len(recipient_list)} recipients")
        
        for i, recipient in enumerate(recipient_list):
            print(f"\\nSending email {i+1}/{len(recipient_list)} to: {recipient}")
            
            # Send email
            success, sender_email, error_msg = self.send_single_email(
                recipient, 
                subject=subject, 
                template_name=template_name
            )
            
            stats['total_attempted'] += 1
            
            if success:
                stats['successful'] += 1
                stats['successful_emails'].append(recipient)
                print(f"✓ Email sent successfully from {sender_email}")
            else:
                stats['failed'] += 1
                stats['failed_emails'].append(recipient)
                stats['errors'].append(f"{recipient}: {error_msg}")
                print(f"✗ Failed to send email: {error_msg}")
            
            # Add delay between emails (except for the last one)
            if i < len(recipient_list) - 1:
                delay = random.randint(delay_range[0], delay_range[1])
                print(f"Waiting {delay} seconds before next email...")
                sleep(delay)
        
        # Print final statistics
        print(f"\\n=== Bulk Email Send Complete ===")
        print(f"Total attempted: {stats['total_attempted']}")
        print(f"Successful: {stats['successful']}")
        print(f"Failed: {stats['failed']}")
        print(f"Success rate: {(stats['successful']/stats['total_attempted']*100):.2f}%")
        
        return stats
    
    def send_from_file(self, email_file: str, subject: str = None, template_name: str = None, delay_range: Tuple[int, int] = (5, 15), max_emails: int = None) -> Dict:
        """
        Send emails to recipients from a file
        
        Args:
            email_file (str): Path to file containing email addresses (one per line)
            subject (str): Email subject
            template_name (str): Template name to use
            delay_range (Tuple[int, int]): Delay range between emails
            max_emails (int): Maximum number of emails to send
            
        Returns:
            Dict: Statistics about the sending process
        """
        try:
            with open(email_file, 'r', encoding='utf-8') as f:
                emails = [line.strip() for line in f.readlines() if line.strip()]
            
            print(f"Loaded {len(emails)} email addresses from {email_file}")
            return self.send_bulk_emails(emails, subject, template_name, delay_range, max_emails)
            
        except FileNotFoundError:
            print(f"Error: Email file {email_file} not found")
            return {}
        except Exception as e:
            print(f"Error reading email file: {e}")
            return {}
    
    def list_templates(self):
        """List all available templates"""
        if not self.email_templates:
            print("No templates configured")
            return
        
        print("Available templates:")
        for template in self.email_templates:
            print(f"- {template['name']}")
    
    def list_accounts(self):
        """List all configured email accounts"""
        if not self.email_accounts:
            print("No email accounts configured")
            return
        
        print("Configured email accounts:")
        for i, account in enumerate(self.email_accounts):
            print(f"{i}: {account['sender_email']}")


# Example usage
if __name__ == "__main__":
    sender = EmailSender()
    
    # List available templates and accounts
    sender.list_templates()
    sender.list_accounts()
    
    # Send single email (uncomment to use)
    # success, sender_email, error = sender.send_single_email(
    #     "recipient@example.com",
    #     subject="Test Email",
    #     template_name="basic_outreach"
    # )
    # print(f"Email {'sent' if success else 'failed'}: {error}")
    
    # Send bulk emails from file (uncomment to use)
    # stats = sender.send_from_file(
    #     "email_list.txt",
    #     subject="Bulk Email Test",
    #     template_name="basic_outreach",
    #     max_emails=5
    # )
