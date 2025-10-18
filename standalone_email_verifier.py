import smtplib
import dns.resolver
import random
import re
import socks
import socket
import requests
import base64
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
        
        # Proxy configuration - Oxylabs HTTP proxy
        self.proxy_config = {
            'host': 'pr.oxylabs.io',
            'port': 7777,
            'username': 'customer-Benjamin_AeM1y-cc-us',
            'password': 'vTteud=9HmU2fP3',
            'type': 'http'
        }
    
    def is_valid_email_format(self, email: str) -> bool:
        """
        Check if email has valid format using regex
        """
        email_regex = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
        return bool(re.match(email_regex, email))
    
    def test_proxy_connection(self) -> bool:
        """
        Test if the HTTP proxy connection is working
        """
        try:
            print("Testing HTTP proxy connection...")
            
            # Create proxy URL
            proxy_url = f"http://{self.proxy_config['username']}:{self.proxy_config['password']}@{self.proxy_config['host']}:{self.proxy_config['port']}"
            
            proxies = {
                'http': proxy_url,
                'https': proxy_url
            }
            
            # Test with a simple HTTP request
            response = requests.get('http://httpbin.org/ip', proxies=proxies, timeout=10)
            
            if response.status_code == 200:
                print(f"✓ HTTP proxy connection successful. IP: {response.json().get('origin', 'Unknown')}")
                return True
            else:
                print(f"✗ HTTP proxy returned status code: {response.status_code}")
                return False
                
        except Exception as e:
            print(f"✗ HTTP proxy connection failed: {e}")
            return False
    
    def verify_email_dns_smtp(self, email: str, use_proxy: bool = False) -> bool:
        """
        Verify email using DNS MX records and SMTP validation
        
        Args:
            email (str): Email address to verify
            use_proxy (bool): Whether to use proxy for connection
            
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
            
            # Try direct connection first, then proxy if it fails
            if not use_proxy:
                try:
                    return self._verify_smtp_direct(email, mx_record)
                except Exception as e:
                    print(f"Direct connection failed for {email}: {e}")
                    print("Attempting verification with HTTP proxy...")
                    return self._verify_smtp_http_connect_proxy(email, mx_record)
            else:
                return self._verify_smtp_http_connect_proxy(email, mx_record)
            
        except dns.resolver.NoAnswer:
            print(f"No MX records found for domain: {domain}")
            return False
        except dns.resolver.NXDOMAIN:
            print(f"Domain does not exist: {domain}")
            return False
        except Exception as e:
            print(f"Error verifying {email}: {e}")
            return False
    
    def _verify_smtp_direct(self, email: str, mx_record: str) -> bool:
        """Direct SMTP verification without proxy"""
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
    
    def _verify_smtp_http_connect_proxy(self, email: str, mx_record: str) -> bool:
        """SMTP verification through HTTP CONNECT proxy"""
        try:
            print(f"Connecting to {mx_record}:25 via HTTP CONNECT proxy...")
            
            # Create socket and connect to proxy
            proxy_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            proxy_socket.settimeout(15)
            proxy_socket.connect((self.proxy_config['host'], self.proxy_config['port']))
            
            # Create authorization header
            auth_string = f"{self.proxy_config['username']}:{self.proxy_config['password']}"
            auth_bytes = base64.b64encode(auth_string.encode()).decode()
            
            # Send CONNECT request
            connect_request = f"CONNECT {mx_record}:25 HTTP/1.1\r\n"
            connect_request += f"Host: {mx_record}:25\r\n"
            connect_request += f"Proxy-Authorization: Basic {auth_bytes}\r\n"
            connect_request += "Connection: keep-alive\r\n\r\n"
            
            proxy_socket.send(connect_request.encode())
            
            # Read response
            response = proxy_socket.recv(1024).decode()
            print(f"Proxy response: {response.split()[1] if len(response.split()) > 1 else 'Unknown'}")
            
            if "200" not in response:
                print(f"Proxy CONNECT failed: {response}")
                proxy_socket.close()
                return False
            
            # Now use the connected socket for SMTP
            server = smtplib.SMTP()
            server.sock = proxy_socket
            server.file = proxy_socket.makefile('rb')
            
            # Get the welcome message
            code, msg = server.getreply()
            if code != 220:
                print(f"SMTP server error: {code} {msg}")
                return False
            
            # Send HELO
            server.helo()
            
            # Use random test email for verification
            test_email = random.choice(self.test_emails)
            server.mail(test_email)
            
            # Check if recipient email exists
            code, response = server.rcpt(email)
            
            # Clean up
            try:
                server.quit()
            except:
                pass
            
            print(f"HTTP CONNECT Proxy SMTP response for {email}: {code} {response}")
            return code == 250  # 250 means the email exists
            
        except Exception as e:
            print(f"HTTP CONNECT proxy verification error for {email}: {e}")
            return False
    
    def verify_email_list(self, email_list: List[str], show_progress: bool = True, force_proxy: bool = False) -> Tuple[List[str], List[str]]:
        """
        Verify a list of emails
        
        Args:
            email_list (List[str]): List of emails to verify
            show_progress (bool): Whether to show progress
            force_proxy (bool): Whether to force proxy usage for all connections
            
        Returns:
            Tuple[List[str], List[str]]: (valid_emails, invalid_emails)
        """
        valid_emails = []
        invalid_emails = []
        total = len(email_list)
        
        for i, email in enumerate(email_list):
            if show_progress:
                print(f"Verifying {i+1}/{total}: {email}")
            
            if self.verify_email_dns_smtp(email, use_proxy=force_proxy):
                valid_emails.append(email)
                if show_progress:
                    print(f"✓ Valid: {email}")
            else:
                invalid_emails.append(email)
                if show_progress:
                    print(f"✗ Invalid: {email}")
        
        return valid_emails, invalid_emails
    
    def verify_from_file(self, input_file: str, output_valid_file: str = None, output_invalid_file: str = None, force_proxy: bool = False) -> dict:
        """
        Verify emails from a file and optionally save results
        
        Args:
            input_file (str): Path to file containing emails (one per line)
            output_valid_file (str): Path to save valid emails
            output_invalid_file (str): Path to save invalid emails
            force_proxy (bool): Whether to force proxy usage for all connections
            
        Returns:
            dict: Statistics about verification
        """
        try:
            with open(input_file, 'r', encoding='utf-8') as f:
                emails = [line.strip() for line in f.readlines() if line.strip()]
            
            print(f"Found {len(emails)} emails to verify")
            if force_proxy:
                print("Using proxy for all connections")
            
            valid_emails, invalid_emails = self.verify_email_list(emails, force_proxy=force_proxy)
            
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
    
    # Test proxy connection first
    print("Testing proxy connectivity...")
    proxy_works = verifier.test_proxy_connection()
    print(f"Proxy status: {'Working' if proxy_works else 'Not working'}\n")
    
    # Test single email
    test_email = "arp@mccarthylebit.com"
    result = verifier.verify_email_dns_smtp(test_email)
    print(f"Email {test_email} is {'valid' if result else 'invalid'}")
    
    # Test with proxy explicitly
    print("\nTesting with proxy:")
    result_proxy = verifier.verify_email_dns_smtp(test_email, use_proxy=True)
    print(f"Email {test_email} via proxy is {'valid' if result_proxy else 'invalid'}")
    
    # Test from file (uncomment to use)
    # Normal verification (proxy as fallback)
    # verifier.verify_from_file(
    #     "emails_to_verify.txt",
    #     "valid_emails.txt",
    #     "invalid_emails.txt"
    # )
    
    # Force proxy usage for all connections
    # verifier.verify_from_file(
    #     "emails_to_verify.txt",
    #     "valid_emails_proxy.txt",
    #     "invalid_emails_proxy.txt",
    #     force_proxy=True
    # )
