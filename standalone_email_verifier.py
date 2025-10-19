import smtplib
import dns.resolver
import random
import re
from typing import List, Tuple


class EmailVerifier:
    """
    Standalone email verification system using DNS and SMTP validation
    """
    
    def __init__(self):
        # Test emails for SMTP verification
        self.test_emails = [
            "zaryabhaider8885@gmail.com", 
            "shahzebnaveed621@gmail.com", 
            "shahzebnaveed622@gmail.com", 
            "shahzebnaveed623@gmail.com", 
            "shahzebnaveed624@gmail.com", 
            "shahzebnaveed625@gmail.com", 
            "zaryabhaider8888@gmail.com",
            "arp@mccarthylebit.com"
        ]
    
    def is_valid_email_format(self, email: str) -> bool:
        """
        Check if email has valid format using regex
        """
        email_regex = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
        return bool(re.match(email_regex, email))
    
    def verify_email_dns_smtp(self, email: str) -> bool:
        """
        Verify email using DNS MX records and SMTP validation
        
        Args:
            email (str): Email address to verify
            
        Returns:
            bool: True if email exists, False otherwise
        """
        if not self.is_valid_email_format(email):
            print(f"Invalid email format: {email}")
            return False
            
        domain = email.split('@')[1]
        
        try:
            # Get MX records for the domain
            mx_records = dns.resolver.resolve(domain, 'MX')
            mx_record = str(mx_records[0].exchange)
            
            # Connect to the SMTP server
            server = smtplib.SMTP(mx_record, timeout=10)
            server.set_debuglevel(0)
            server.helo()
            
            # Use random test email for verification
            test_email = random.choice(self.test_emails)
            server.mail(test_email)
            
            # Check if recipient email exists
            code, _ = server.rcpt(email)
            server.quit()
            
            return code == 250  # 250 means the email exists
            
        except dns.resolver.NoAnswer:
            print(f"No MX records found for domain: {domain}")
            return False
        except dns.resolver.NXDOMAIN:
            print(f"Domain does not exist: {domain}")
            return False
        except Exception as e:
            print(f"Error verifying {email}: {e}")
            return False
    
    def verify_email_list(self, email_list: List[str], show_progress: bool = True) -> Tuple[List[str], List[str]]:
        """
        Verify a list of emails
        
        Args:
            email_list (List[str]): List of emails to verify
            show_progress (bool): Whether to show progress
            
        Returns:
            Tuple[List[str], List[str]]: (valid_emails, invalid_emails)
        """
        valid_emails = []
        invalid_emails = []
        total = len(email_list)
        
        for i, email in enumerate(email_list):
            if show_progress:
                print(f"Verifying {i+1}/{total}: {email}")
            
            if self.verify_email_dns_smtp(email):
                valid_emails.append(email)
                if show_progress:
                    print(f"✓ Valid: {email}")
            else:
                invalid_emails.append(email)
                if show_progress:
                    print(f"✗ Invalid: {email}")
        
        return valid_emails, invalid_emails
    
    def verify_from_file(self, input_file: str, output_valid_file: str = None, output_invalid_file: str = None) -> dict:
        """
        Verify emails from a file and optionally save results
        
        Args:
            input_file (str): Path to file containing emails (one per line)
            output_valid_file (str): Path to save valid emails
            output_invalid_file (str): Path to save invalid emails
            
        Returns:
            dict: Statistics about verification
        """
        try:
            with open(input_file, 'r', encoding='utf-8') as f:
                emails = [line.strip() for line in f.readlines() if line.strip()]
            
            print(f"Found {len(emails)} emails to verify")
            
            valid_emails, invalid_emails = self.verify_email_list(emails)
            
            # Save results if output files specified
            if output_valid_file:
                with open(output_valid_file, 'w', encoding='utf-8') as f:
                    for email in valid_emails:
                        f.write(email + '\n')
                print(f"Valid emails saved to: {output_valid_file}")
            
            if output_invalid_file:
                with open(output_invalid_file, 'w', encoding='utf-8') as f:
                    for email in invalid_emails:
                        f.write(email + '\n')
                print(f"Invalid emails saved to: {output_invalid_file}")
            
            stats = {
                'total': len(emails),
                'valid': len(valid_emails),
                'invalid': len(invalid_emails),
                'valid_percentage': (len(valid_emails) / len(emails)) * 100 if emails else 0
            }
            
            print(f"\nVerification Results:")
            print(f"Total emails: {stats['total']}")
            print(f"Valid emails: {stats['valid']}")
            print(f"Invalid emails: {stats['invalid']}")
            print(f"Valid percentage: {stats['valid_percentage']:.2f}%")
            
            return stats
            
        except FileNotFoundError:
            print(f"Error: File {input_file} not found")
            return {}
        except Exception as e:
            print(f"Error processing file: {e}")
            return {}


# Example usage
if __name__ == "__main__":
    verifier = EmailVerifier()
    
    # Test single email
    test_email = "arp@mccarthylebit.com"
    result = verifier.verify_email_dns_smtp(test_email)
    print(f"Email {test_email} is {'valid' if result else 'invalid'}")
    
    # Test from file (uncomment to use)
    # verifier.verify_from_file(
    #     "emails_to_verify.txt",
    #     "valid_emails.txt",
    #     "invalid_emails.txt"
    # )
