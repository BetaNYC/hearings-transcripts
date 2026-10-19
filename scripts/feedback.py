"""The "report a mistake" link that every generated page carries in its footer.

Python 3.11 to 3.14, standard library only. No network access.

The link opens a new GitHub issue with the correction form (.github/ISSUE_TEMPLATE/correction.yml)
and fills in what the page already knows. URL query parameters, as documented by GitHub:

- `template`, `title`: "Creating an issue from a URL query",
  https://docs.github.com/en/issues/tracking-your-work-with-issues/using-issues/creating-an-issue#creating-an-issue-from-a-url-query
- issue-form fields by their `id` ("the `id` is the canonical identifier for the field in URL
  query parameter prefills"), https://docs.github.com/en/communities/using-templates-to-encourage-useful-issues-and-pull-requests/syntax-for-githubs-form-schema#keys

No `labels` parameter: it needs permission to label, which most readers do not have, and the
repository has no correction label (checked with `gh label list` on 2026-10-19).
"""

from __future__ import annotations

import html
import urllib.parse

ISSUES_NEW = "https://github.com/BetaNYC/hearings-transcripts/issues/new"
SITE = "https://betanyc.github.io/hearings-transcripts/"
TEMPLATE = "correction.yml"  # .github/ISSUE_TEMPLATE/correction.yml; field ids below must match it
FIELD_HEARING, FIELD_PAGE = "hearing", "page"
TEXT = "See a mistake, a wrong name or a missing document?"


def hearing_label(hearing: dict | None) -> str:
    if not hearing:
        return ""
    return f"{hearing['date']}, {hearing['body']}: {hearing['title']}"


def issue_url(page_rel: str, hearing: dict | None) -> str:
    """New-issue URL for a page (path relative to the site root) of a hearing (None for pages
    that cover every hearing, such as index.html)."""
    page = SITE + page_rel
    what = f"{hearing['date']} {hearing['body'].removeprefix('NYC Council ')}" if hearing else "the site"
    params = {"template": TEMPLATE, "title": f"Correction: {what}, {page_rel}",
              FIELD_PAGE: page}
    if hearing:
        params[FIELD_HEARING] = hearing_label(hearing)
    return ISSUES_NEW + "?" + urllib.parse.urlencode(params, quote_via=urllib.parse.quote)


def feedback_html(page_rel: str, hearing: dict | None) -> str:
    url = html.escape(issue_url(page_rel, hearing), quote=True)
    return (f'<p class="feedback">{html.escape(TEXT)} '
            f'<a href="{url}">Open an issue on GitHub</a>.</p>')
