"""Deliver the user's existing API credential encrypted to their mini1 key."""
import os,subprocess,hashlib,json
from pathlib import Path
PUBLIC_KEY='-----BEGIN PUBLIC KEY-----\nMIIBojANBgkqhkiG9w0BAQEFAAOCAY8AMIIBigKCAYEA5S9OgQes6BudqQpWzM38\nHKyM522Nlc5wz8gnm1pBWPxr4IRH/34aNGEZhOoO5Orrzmk4aM+KYrz+79LGG38U\nobkga0WRXABOEN6Tcq27/Iv/ASzz4tbIanrXYVTpT/W5tzH3iEdDpGM4yMXqrKaV\nnoX+IotvwhH2d3zO07J+a45zvSgwwrVS8iQRVlA1MguMo4QdHufjkdbGksJf1iNp\n1wTtrXB8tHDQbRcRXVToknd6ukpOLABiztbYmt/0JU3Tma4QfhhDNU8TD69Ivcev\n0TPwajWSxfRuRQgb6OSpLa+nartKZ63oub1DWYTpcsVuY9R6QpYE2QxFFdtTisow\nuMyWgiVEJIpWOv+DQyORvLUAbN2139QsFqdYLp5nqyMbHpLSJai+WDJior3W4G6W\nX8kIWeJbDJQbFVGgIXL7a+AJ2MmbrIjL87gF5LicwkLgDCliF8kxrF4cfu+S66kG\nXNuMPNfvMl+efUqDIL3k52AjP1LY5/GTS3WpObSBR5ppAgMBAAE=\n-----END PUBLIC KEY-----\n'
key=os.environ.get('BIZINFO_API_KEY','')
if not key:raise SystemExit('Configured credential is missing')
Path('recipient-public.pem').write_text(PUBLIC_KEY)
r=subprocess.run(['openssl','pkeyutl','-encrypt','-pubin','-inkey','recipient-public.pem','-pkeyopt','rsa_padding_mode:oaep','-pkeyopt','rsa_oaep_md:sha256','-pkeyopt','rsa_mgf1_md:sha256'],input=key.encode(),capture_output=True)
if r.returncode:raise SystemExit('Credential encryption failed')
Path('credential.enc').write_bytes(r.stdout)
Path('transfer.json').write_text(json.dumps({'recipient_public_sha256':hashlib.sha256(PUBLIC_KEY.encode()).hexdigest(),'ciphertext_sha256':hashlib.sha256(r.stdout).hexdigest(),'encryption':'RSA-OAEP SHA256','plaintext_logged_or_uploaded':False},indent=2))
print('Encrypted for mini1; plaintext not emitted')
