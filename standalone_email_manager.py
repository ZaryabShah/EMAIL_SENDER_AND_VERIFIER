import os
from typing import List, Set, Dict
from datetime import datetime


class EmailListManager:
    """
    Standalone email list management system for handling email queues, duplicates, and tracking
    """
    
    def __init__(self, base_directory: str = "email_data"):
        """
        Initialize EmailListManager
        
        Args:
            base_directory (str): Directory to store email list files
        """
        self.base_directory = base_directory
        self.ensure_directory_exists()
        
        # File paths
        self.queue_file = os.path.join(base_directory, "email_queue.txt")
        self.sent_file = os.path.join(base_directory, "sent_emails.txt")
        self.failed_file = os.path.join(base_directory, "failed_emails.txt")
        self.verified_file = os.path.join(base_directory, "verified_emails.txt")
        self.invalid_file = os.path.join(base_directory, "invalid_emails.txt")
        self.log_file = os.path.join(base_directory, "email_log.txt")
    
    def ensure_directory_exists(self):
        """Create base directory if it doesn't exist"""
        if not os.path.exists(self.base_directory):
            os.makedirs(self.base_directory)
            print(f"Created directory: {self.base_directory}")
    
    def log_action(self, action: str, details: str = ""):
        """Log actions with timestamp"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = f"[{timestamp}] {action}"
        if details:
            log_entry += f" - {details}"
        
        with open(self.log_file, 'a', encoding='utf-8') as f:
            f.write(log_entry + '\\n')
    
    def read_email_list(self, file_path: str) -> List[str]:
        """
        Read emails from a file
        
        Args:
            file_path (str): Path to the email file
            
        Returns:
            List[str]: List of email addresses
        """
        try:
            if not os.path.exists(file_path):
                return []
            
            with open(file_path, 'r', encoding='utf-8') as f:
                emails = [line.strip() for line in f.readlines() if line.strip()]
            
            return emails
        except Exception as e:
            print(f"Error reading {file_path}: {e}")
            return []
    
    def write_email_list(self, emails: List[str], file_path: str, mode: str = 'w'):
        """
        Write emails to a file
        
        Args:
            emails (List[str]): List of email addresses
            file_path (str): Path to the email file
            mode (str): File write mode ('w' for overwrite, 'a' for append)
        """
        try:
            with open(file_path, mode, encoding='utf-8') as f:
                for email in emails:
                    f.write(email + '\\n')
        except Exception as e:
            print(f"Error writing to {file_path}: {e}")
    
    def add_emails_to_queue(self, emails: List[str], source: str = "manual") -> int:
        """
        Add emails to the sending queue
        
        Args:
            emails (List[str]): List of email addresses to add
            source (str): Source description for logging
            
        Returns:
            int: Number of emails added
        """
        # Filter out invalid formats and duplicates
        valid_emails = []
        existing_emails = set(self.get_all_processed_emails())
        
        for email in emails:
            email = email.strip().lower()
            if self.is_valid_email_format(email) and email not in existing_emails:
                valid_emails.append(email)
                existing_emails.add(email)
        
        if valid_emails:
            self.write_email_list(valid_emails, self.queue_file, mode='a')
            self.log_action(f"Added {len(valid_emails)} emails to queue", f"Source: {source}")
        
        return len(valid_emails)
    
    def add_emails_from_file(self, input_file: str, source: str = None) -> int:
        """
        Add emails from a file to the queue
        
        Args:
            input_file (str): Path to input file containing emails
            source (str): Source description
            
        Returns:
            int: Number of emails added
        """
        emails = self.read_email_list(input_file)
        source_desc = source or f"file: {input_file}"
        return self.add_emails_to_queue(emails, source_desc)
    
    def get_next_email(self) -> str:
        """
        Get the next email from the queue
        
        Returns:
            str: Next email address or empty string if queue is empty
        """
        emails = self.read_email_list(self.queue_file)
        
        if emails:
            next_email = emails[0]
            # Update queue file without the first email
            remaining_emails = emails[1:]
            self.write_email_list(remaining_emails, self.queue_file)
            return next_email
        
        return ""
    
    def mark_email_sent(self, email: str, sender_account: str = ""):
        """
        Mark an email as successfully sent
        
        Args:
            email (str): Email address that was sent to
            sender_account (str): Sender account used
        """
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        entry = f"{email}"
        if sender_account:
            entry += f" (sent from: {sender_account})"
        entry += f" - {timestamp}"
        
        with open(self.sent_file, 'a', encoding='utf-8') as f:
            f.write(entry + '\\n')
        
        self.log_action("Email sent", f"To: {email}, From: {sender_account}")
    
    def mark_email_failed(self, email: str, error_reason: str = "", sender_account: str = ""):
        """
        Mark an email as failed to send
        
        Args:
            email (str): Email address that failed
            error_reason (str): Reason for failure
            sender_account (str): Sender account used
        """
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        entry = f"{email}"
        if error_reason:
            entry += f" (Error: {error_reason})"
        if sender_account:
            entry += f" (attempted from: {sender_account})"
        entry += f" - {timestamp}"
        
        with open(self.failed_file, 'a', encoding='utf-8') as f:
            f.write(entry + '\\n')
        
        self.log_action("Email failed", f"To: {email}, Error: {error_reason}")
    
    def mark_emails_verified(self, valid_emails: List[str], invalid_emails: List[str]):
        """
        Mark emails as verified or invalid
        
        Args:
            valid_emails (List[str]): List of valid email addresses
            invalid_emails (List[str]): List of invalid email addresses
        """
        if valid_emails:
            self.write_email_list(valid_emails, self.verified_file, mode='a')
            self.log_action(f"Verified {len(valid_emails)} valid emails")
        
        if invalid_emails:
            self.write_email_list(invalid_emails, self.invalid_file, mode='a')
            self.log_action(f"Marked {len(invalid_emails)} emails as invalid")
    
    def get_all_processed_emails(self) -> Set[str]:
        """
        Get all emails that have been processed (sent, failed, or marked invalid)
        
        Returns:
            Set[str]: Set of all processed email addresses
        """
        processed = set()
        
        # Add sent emails
        sent_emails = self.read_email_list(self.sent_file)
        for entry in sent_emails:
            email = entry.split()[0]  # Get first part (email address)
            processed.add(email.lower())
        
        # Add failed emails
        failed_emails = self.read_email_list(self.failed_file)
        for entry in failed_emails:
            email = entry.split()[0]  # Get first part (email address)
            processed.add(email.lower())
        
        # Add invalid emails
        invalid_emails = self.read_email_list(self.invalid_file)
        for email in invalid_emails:
            processed.add(email.lower())
        
        return processed
    
    def remove_duplicates_from_queue(self) -> int:
        """
        Remove duplicate emails from the queue
        
        Returns:
            int: Number of duplicates removed
        """
        queue_emails = self.read_email_list(self.queue_file)
        processed_emails = self.get_all_processed_emails()
        
        # Remove duplicates and already processed emails
        unique_emails = []
        seen = set()
        duplicates_removed = 0
        
        for email in queue_emails:
            email_lower = email.lower()
            if email_lower not in seen and email_lower not in processed_emails:
                unique_emails.append(email)
                seen.add(email_lower)
            else:
                duplicates_removed += 1
        
        # Write back unique emails
        self.write_email_list(unique_emails, self.queue_file)
        
        if duplicates_removed > 0:
            self.log_action(f"Removed {duplicates_removed} duplicate emails from queue")
        
        return duplicates_removed
    
    def get_statistics(self) -> Dict:
        """
        Get statistics about email processing
        
        Returns:
            Dict: Statistics dictionary
        """
        queue_emails = self.read_email_list(self.queue_file)
        sent_emails = self.read_email_list(self.sent_file)
        failed_emails = self.read_email_list(self.failed_file)
        verified_emails = self.read_email_list(self.verified_file)
        invalid_emails = self.read_email_list(self.invalid_file)
        
        stats = {
            'queue_count': len(queue_emails),
            'sent_count': len(sent_emails),
            'failed_count': len(failed_emails),
            'verified_count': len(verified_emails),
            'invalid_count': len(invalid_emails),
            'total_processed': len(sent_emails) + len(failed_emails),
            'success_rate': 0
        }
        
        if stats['total_processed'] > 0:
            stats['success_rate'] = (stats['sent_count'] / stats['total_processed']) * 100
        
        return stats
    
    def print_statistics(self):
        """Print formatted statistics"""
        stats = self.get_statistics()
        
        print("\\n=== Email List Statistics ===")
        print(f"Emails in queue: {stats['queue_count']}")
        print(f"Successfully sent: {stats['sent_count']}")
        print(f"Failed to send: {stats['failed_count']}")
        print(f"Verified emails: {stats['verified_count']}")
        print(f"Invalid emails: {stats['invalid_count']}")
        print(f"Total processed: {stats['total_processed']}")
        print(f"Success rate: {stats['success_rate']:.2f}%")
        print("=" * 30)
    
    def is_valid_email_format(self, email: str) -> bool:
        """Basic email format validation"""
        import re
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}$'
        return bool(re.match(pattern, email))
    
    def clear_all_data(self, confirm: bool = False):
        """
        Clear all email data (use with caution)
        
        Args:
            confirm (bool): Must be True to actually clear data
        """
        if not confirm:
            print("To clear all data, call with confirm=True")
            return
        
        files_to_clear = [
            self.queue_file, self.sent_file, self.failed_file,
            self.verified_file, self.invalid_file, self.log_file
        ]
        
        for file_path in files_to_clear:
            if os.path.exists(file_path):
                os.remove(file_path)
        
        print("All email data cleared")
    
    def export_data(self, export_directory: str = "export"):
        """
        Export all data to a specified directory
        
        Args:
            export_directory (str): Directory to export data to
        """
        if not os.path.exists(export_directory):
            os.makedirs(export_directory)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        files_to_export = {
            'queue': self.queue_file,
            'sent': self.sent_file,
            'failed': self.failed_file,
            'verified': self.verified_file,
            'invalid': self.invalid_file,
            'log': self.log_file
        }
        
        for name, source_file in files_to_export.items():
            if os.path.exists(source_file):
                export_file = os.path.join(export_directory, f"{name}_emails_{timestamp}.txt")
                with open(source_file, 'r', encoding='utf-8') as src:
                    with open(export_file, 'w', encoding='utf-8') as dst:
                        dst.write(src.read())
        
        print(f"Data exported to {export_directory}")


# Example usage
if __name__ == "__main__":
    manager = EmailListManager()
    
    # Add some test emails
    test_emails = ["test1@example.com", "test2@example.com", "invalid-email"]
    added = manager.add_emails_to_queue(test_emails, "test")
    print(f"Added {added} emails to queue")
    
    # Show statistics
    manager.print_statistics()
    
    # Get next email
    next_email = manager.get_next_email()
    if next_email:
        print(f"Next email to process: {next_email}")
        # Simulate sending
        manager.mark_email_sent(next_email, "test@sender.com")
    
    # Show updated statistics
    manager.print_statistics()
