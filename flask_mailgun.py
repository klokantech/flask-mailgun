import logging
import requests

from flask import current_app, render_template_string
from html2text import html2text


default_api_url_template = (
    'https://api.mailgun.net/v3/{domain}/messages')


default_debug_template = """\
Mailgun send

From:       %(from)s
To:         %(to)s
Subject:    %(subject)s

%(text)s

----------------------------------------

%(html)s
"""


default_logging_template = """\
Severity:   %(levelname)s
Location:   %(pathname)s:%(lineno)d
Module:     %(module)s
Function:   %(funcName)s
Time:       %(asctime)s

%(message)s
"""


default_error_subject_withexcinfo_template = 'ERROR: {exc_info}'
default_error_subject_withoutexcinfo_template = (
    '{levelname}: {pathname}:{lineno}')


default_error_template = """\
{% autoescape false -%}
{{ message }}

{{ request.method }} {{ request.url }}
{% for key, val in request.headers.items()|sort -%}
{{ key }}: {{ val }}
{% endfor -%}
{% for key, val in session.items()|sort -%}
Session: {{ key }}={{ val }}
{% endfor %}
{% for key, val in request.form.items()|sort -%}
{{ key }}={{ val }}
{% endfor %}
{% endautoescape %}
"""


default_api_error_template = (
    'Mailgun API {method} at {url} failed '
    'with status code {status_code}:\n{text}')


class Mailgun(object):
    """Mailgun integration for Flask."""

    def __init__(self, app=None):
        self.debug = None
        self.domain = None
        self.key = None

        self.api_url_template = None
        self.debug_template = None
        self.logging_template = None

        self.error_subject_withexcinfo_template = None
        self.error_subject_withoutexcinfo_template = None
        self.error_template = None

        self.api_error_template = None

        if app is not None:
            self.init_app(app)

    def init_app(self, app):
        """Inititialize the extension.

        There are two configuration options for authentication:
        MAILGUN_DOMAIN and MAILGUN_KEY. They are not necessary
        in debug mode.

        The extension can also setup a custom logging handler that
        sends emails for events at level ERROR and above. Configure
        the MAILGUN_LOGGING_RECIPIENT configuration option to enable
        this, it is an email address where messages will be sent.
        Optionally, you can configure the sender address as well
        with the MAILGUN_LOGGING_SENDER option.

        There are also several template strings that can be optionally
        configured. If not configured, they fall back to default
        values. These options are:
          - MAILGUN_API_URL_TEMPLATE
          - MAILGUN_DEBUG_TEMPLATE
          - MAILGUN_LOGGING_TEMPLATE
          - MAILGUN_ERROR_SUBJECT_WITHEXCINFO_TEMPLATE
          - MAILGUN_ERROR_SUBJECT_WITHOUTEXCINFO_TEMPLATE
          - MAILGUN_ERROR_TEMPLATE
          - MAILGUN_API_ERROR_TEMPLATE
        """
        app.extensions['mailgun'] = self
        self.debug = app.debug

        self.domain = app.config['MAILGUN_DOMAIN']
        self.key = app.config['MAILGUN_KEY']

        self.api_url_template = app.config.get(
            'MAILGUN_API_URL_TEMPLATE')
        if self.api_url_template is None:
            self.api_url_template = default_api_url_template

        if self.debug:
            app.config.setdefault('MAILGUN_DOMAIN', 'TESTING')
            app.config.setdefault('MAILGUN_KEY', '')

            self.debug_template = app.config.get('MAILGUN_DEBUG_TEMPLATE')
            if self.debug_template is None:
                self.debug_template = default_debug_template

        self.logging_template = app.config.get(
            'MAILGUN_LOGGING_TEMPLATE')
        if self.logging_template is None:
            self.logging_template = default_logging_template

        self.error_subject_withexcinfo_template = app.config.get(
            'MAILGUN_ERROR_SUBJECT_WITHEXCINFO_TEMPLATE')
        if self.error_subject_withexcinfo_template is None:
            self.error_subject_withexcinfo_template = (
                default_error_subject_withexcinfo_template)

        self.error_subject_withoutexcinfo_template = app.config.get(
            'MAILGUN_ERROR_SUBJECT_WITHOUTEXCINFO_TEMPLATE')
        if self.error_subject_withoutexcinfo_template is None:
            self.error_subject_withoutexcinfo_template = (
                default_error_subject_withoutexcinfo_template)

        self.error_template = app.config.get(
            'MAILGUN_ERROR_TEMPLATE')
        if self.error_template is None:
            self.error_template = default_error_template

        self.api_error_template = app.config.get(
            'MAILGUN_API_ERROR_TEMPLATE')
        if self.api_error_template is None:
            self.api_error_template = default_api_error_template

        logging_recipient = app.config.get('MAILGUN_LOGGING_RECIPIENT')

        if logging_recipient is not None:
            logging_sender = app.config.get('MAILGUN_LOGGING_SENDER')

            handler = LoggingHandler(
                self, logging_sender, logging_recipient)

            app.logger.addHandler(handler)

    def send(self, **data):
        """Send email. It will not actually send emails in debug mode,
        instead it will log them.

        The `from_` parameter is the sender address, if missing it will be
        'no-reply@domain'. The `to` parameter is the recipient address,
        `subject` is the subject line. Plain text body is in the `text`
        parameter, HTML body in the `html` parameter. At least one of those
        two MUST be specified. If `text` is not specified but `html` is,
        `text` will default to approximate Markdown rendering of `html`.
        """
        from_ = data.pop('from_', None)
        if from_ is None:
            from_ = 'no-reply@{}'.format(self.domain)

        data['from'] = from_

        if 'html' in data and 'text' not in data:
            data['text'] = html2text(data['html'])

        if self.debug:
            data.setdefault('html', '(no HTML)')
            current_app.logger.debug(debug_template, data)
            return

        url = self.api_url_template.format(domain=self.domain)

        response = requests.post(url, auth=('api', self.key), data=data)
        if response.status_code != 200:
            raise APIError(response, self.api_error_template)

        current_app.logger.info(
            'Mailgun sent to {0}'.format(data['to']))


class LoggingHandler(logging.Handler):
    """Logging handler that sends records via Mailgun."""

    def __init__(self, mailgun, sender, recipient):
        super().__init__(level=logging.ERROR)
        self.setFormatter(logging.Formatter(mailgun.logging_template))
        self.mailgun = mailgun
        self.sender = sender
        self.recipient = recipient
        self.messages = []

    def emit(self, record):
        if record.exc_info is not None:
            __, exc, __ = record.exc_info
            subject = (
                self.mailgun
                    .error_subject_withexcinfo_template
                    .format(exc_info=exc))
        else:
            subject = (
                self.mailgun
                    .error_subject_withoutexcinfo_template
                    .format(
                        levelname=record.levelname,
                        pathname=record.pathname,
                        lineno=record.lineno))

        message = self.format(record)
        text = render_template_string(
            self.mailgun.error_template, message=message)

        self.mailgun.send(
            from_=self.sender,
            to=self.recipient,
            subject=subject,
            text=text)


class APIError(Exception):
    """Error response from the Mailgun server."""

    def __init__(self, response, api_error_template):
        self.response = response
        self.api_error_template = api_error_template

    def __str__(self):
        return self.api_error_template.format(
            method=self.response.request.method,
            url=self.response.request.url,
            status_code=self.response.status_code,
            text=self.response.text)
