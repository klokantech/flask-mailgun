import requests

from flask import current_app
from html2text import html2text
from pprint import pformat


class Mailgun:

    """Mailgun integration for Flask."""

    def __init__(self, app=None):
        self.debug = None
        self.domain = None
        self.key = None
        if app is not None:
            self.init_app(app)

    def init_app(self, app):
        """Inititialize the extension. There are two configuration options,
        MAILGUN_DOMAIN and MAILGUN_KEY. They are not necessary in debug mode.
        """
        app.extensions['mailgun'] = self
        self.debug = app.debug
        if not self.debug:
            self.domain = app.config['MAILGUN_DOMAIN']
            self.key = app.config['MAILGUN_KEY']

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
            current_app.logger.debug('Mailgun send:\n%s', pformat(data))
            return
        url = 'https://api.mailgun.net/v3/{}/messages'.format(self.domain)
        response = requests.post(url, auth=('api', self.key), data=data)
        if response.status_code != 200:
            raise MailgunAPIError(response)
        current_app.logger.info('Mailgun sent to %s', data['to'])


class MailgunAPIError(Exception):

    """Error response from the Mailgun server."""

    def __init__(self, response):
        self.response = response

    def __str__(self):
        template = 'Mailgun API {} at {} failed with status code {}:\n{}'
        return template.format(
            self.response.request.method,
            self.response.request.url,
            self.response.status_code,
            self.response.text)
