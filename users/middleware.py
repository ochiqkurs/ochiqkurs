"""Campaign attribution: turn UTM-tagged links into first-party funnel data.

Cloudflare Web Analytics counts clicks at the edge, but it can't join a
campaign to a ``User``, ``Enrollment`` or ``Certificate`` row — which is the
only question worth asking ("which channel produces *learners*?"). This
middleware captures the campaign in the session on the way in;
``users.views.attach_acquisition`` copies it onto the user at sign-in.

Deliberately narrow, so the tables stay small and honest:
  * GET page views only (no /api/, /admin/, /static/, /media/),
  * crawlers are ignored — a bot following a shared campaign link would
    otherwise inflate every number,
  * one ``CampaignHit`` per session *per campaign*, not per pageview,
  * untagged visitors write nothing to the session (so no ``django_session``
    row is created) unless they arrived from an external referrer.

The URL is not rewritten to drop the parameters: the canonical tag is already
query-free (``learning.context_processors.absolute_url(request.path)``), so
tagged links carry no duplicate-content cost.
"""
import re
from urllib.parse import urlparse

from .models import UTM_MAX, CampaignHit

# Session keys: the sticky first-touch record, and the last campaign tuple
# seen (used to dedupe hits without a DB constraint).
SESSION_ATTR_KEY = '_utm_attr'
SESSION_LAST_KEY = '_utm_last'

SKIP_PREFIXES = ('/api/', '/admin/', '/static/', '/media/')
CRAWLER_RE = re.compile(
    r'bot|crawl|spider|slurp|preview|fetch|monitor|curl|wget|python-requests|headless',
    re.IGNORECASE,
)
# Conservative allow-list: campaign values are attacker-controlled query params.
SAFE_VALUE_RE = re.compile(r'^[\w .\-/+:]+$')
MAX_RAW_LENGTH = 200
SEARCH_HOSTS = ('google.', 'bing.', 'yandex.', 'duckduckgo.', 'yahoo.', 'search.brave.')


def clean_utm(value):
    """Normalize one campaign value, or return '' if it isn't usable.

    Lower-cased so ``Instagram`` and ``instagram`` don't split into two
    campaigns; anything with unexpected characters, or absurdly long (a crafted
    URL trying to stuff the table), is dropped rather than stored.
    """
    if not value:
        return ''
    value = ' '.join(value.split())
    if not value or len(value) > MAX_RAW_LENGTH:
        return ''
    value = value.lower()
    if not SAFE_VALUE_RE.match(value):
        return ''
    return value[:UTM_MAX]


def referrer_origin(referrer, host):
    """(source, medium) for an external referrer — ('', '') for same-site/empty."""
    if not referrer:
        return '', ''
    netloc = urlparse(referrer).netloc.lower().split(':')[0]
    if netloc.startswith('www.'):
        netloc = netloc[4:]
    host = (host or '').lower().split(':')[0]
    if host.startswith('www.'):
        host = host[4:]
    if not netloc or netloc == host:
        return '', ''
    medium = 'organic' if netloc.startswith(SEARCH_HOSTS) else 'referral'
    return clean_utm(netloc), medium


class UTMAttributionMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        try:
            self._capture(request)
        except Exception:
            # Attribution is telemetry: it must never break a page render.
            pass
        return self.get_response(request)

    def _capture(self, request):
        if request.method != 'GET' or request.path.startswith(SKIP_PREFIXES):
            return
        user_agent = request.META.get('HTTP_USER_AGENT', '')
        if not user_agent or CRAWLER_RE.search(user_agent):
            return

        params = request.GET
        source = clean_utm(params.get('utm_source'))
        medium = clean_utm(params.get('utm_medium'))
        campaign = clean_utm(params.get('utm_campaign'))
        content = clean_utm(params.get('utm_content'))
        term = clean_utm(params.get('utm_term'))

        # Shorthand for bio/channel links: ?ref=telegram_kanal
        if not source:
            alias = clean_utm(params.get('ref'))
            if alias:
                source, medium = alias, medium or 'referral'

        referrer = request.META.get('HTTP_REFERER', '')[:300]
        session = request.session

        if source or campaign:
            self._record_campaign(
                request, session, source, medium, campaign, content, term, referrer,
            )
            return

        # Untagged visit: remember the first external referrer so a later signup
        # is still attributed (organic/referral) instead of vanishing into
        # "direct". Nothing is written for genuinely direct traffic.
        if SESSION_ATTR_KEY in session:
            return
        ref_source, ref_medium = referrer_origin(referrer, request.get_host())
        if not ref_source:
            return
        session[SESSION_ATTR_KEY] = self._attribution(
            request, ref_source, ref_medium, '', '', '', referrer,
        )

    def _record_campaign(self, request, session, source, medium, campaign, content, term, referrer):
        if SESSION_ATTR_KEY not in session:
            # First touch wins: a later campaign in the same session never
            # overwrites where this visitor originally came from.
            session[SESSION_ATTR_KEY] = self._attribution(
                request, source, medium, campaign, content, term, referrer,
            )

        seen = [source, medium, campaign, content, term]
        if session.get(SESSION_LAST_KEY) == seen:
            return  # same link clicked again in this session — already logged
        session[SESSION_LAST_KEY] = seen

        if session.session_key is None:
            session.save()  # a hit needs a session key to be claimed at login

        CampaignHit.objects.create(
            session_key=session.session_key,
            source=source,
            medium=medium,
            campaign=campaign,
            content=content,
            term=term,
            landing_path=request.path[:200],
            referrer=referrer,
            user=request.user if request.user.is_authenticated else None,
        )

    @staticmethod
    def _attribution(request, source, medium, campaign, content, term, referrer):
        return {
            'source': source,
            'medium': medium,
            'campaign': campaign,
            'content': content,
            'term': term,
            'landing_path': request.path[:200],
            'referrer': referrer,
        }
