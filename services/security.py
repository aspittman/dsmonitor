import re
from urllib.parse import urlsplit


class Sanitizer:
    def __init__(self, secrets=()):
        self.secrets = sorted(set(filter(None, secrets)), key=len, reverse=True)

    def text(self, value):
        text = str(value)
        for secret in self.secrets:
            text = text.replace(secret, '[REDACTED]')
        text = re.sub(r'(?i)(bearer\s+)\S+', r'\1[REDACTED]', text)
        text = re.sub(r'(?i)((?:[\w-]*(?:password|passwd|secret|token|api[_-]?key|service[_-]?role)[\w-]*)[\"\']?\s*[:=]\s*)(?:\"[^\"]*\"|\'[^\']*\'|[^\s,;]+)', r'\1[REDACTED]', text)
        text = re.sub(r'\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+', '[REDACTED]', text)
        text = re.sub(r'\b(?:sk|sb_secret|sb_publishable)[_-][A-Za-z0-9_-]{12,}', '[REDACTED]', text)
        text = re.sub(r'(?:https?|postgres(?:ql)?)://[^\s<>\"\']+', '[URL REDACTED]', text)
        text = re.sub(r'\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b', '[EMAIL REDACTED]', text)
        return text[:2000]

    def clean(self, value):
        if isinstance(value, dict):
            return {k: self.clean(v) for k, v in value.items() if not re.search(r'(?i)password|secret|token|credential', k)}
        if isinstance(value, list):
            return [self.clean(v) for v in value]
        return self.text(value) if isinstance(value, str) else value


def validate_url(url):
    p = urlsplit(url)
    if p.username or p.password or p.fragment or p.query:
        raise ValueError('Endpoint must not contain credentials, query or fragment')
    if p.scheme != 'https' and not (p.scheme == 'http' and p.hostname in ('127.0.0.1', 'localhost', '::1')):
        raise ValueError('HTTPS required except for loopback endpoints')
    if not p.hostname:
        raise ValueError('Endpoint hostname missing')
    return url.rstrip('/')
