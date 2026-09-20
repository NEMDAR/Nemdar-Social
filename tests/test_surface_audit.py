import unittest
from unittest.mock import patch
from server.surface_audit import summarize_html,validate_public_url

class SurfaceAuditTests(unittest.TestCase):
 def test_extracts_public_conversion_signals(self):
  html=b'''<html><head><meta charset="utf-8"><title>Example Brand</title><meta name="description" content="Clear value proposition"><meta name="viewport" content="width=device-width"><script type="application/ld+json">{}</script><script>gtag('config','G-X')</script></head><body><form></form><a href="https://wa.me/971500000000">Chat</a><a href="https://instagram.com/example">Instagram</a></body></html>'''
  result=summarize_html(html,'https://example.com',200,'text/html')
  self.assertEqual(result['title'],'Example Brand');self.assertEqual(result['description'],'Clear value proposition')
  self.assertTrue(result['signals']['whatsApp']);self.assertTrue(result['signals']['analytics']);self.assertTrue(result['signals']['structuredData']);self.assertEqual(result['signals']['forms'],1)
 def test_blocks_private_and_credentialed_urls(self):
  for value in ['http://127.0.0.1','http://[::1]','http://user:pass@example.com','ftp://example.com/file']:
   with self.assertRaises(ValueError):validate_public_url(value)

if __name__=='__main__':unittest.main()
