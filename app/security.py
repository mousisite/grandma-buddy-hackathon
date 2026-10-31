# app/security.py
# Only Grandma Buddy's own page may use the app's /api.
#
# Buddy runs on her computer, and her browser can have other websites open.
# Without these checks, any website could quietly send requests to
# http://localhost:8000: add a doctor question, paint a Memory book page
# (which costs money), or ask for her doctor notes (an AI call).
# - Browsers say where each request comes from (the Sec-Fetch-Site and
#   Origin headers). An /api request from another website, or from another
#   port on this computer, is refused.
# - A request addressed to any host name other than this computer's is
#   refused, so a website's name pointed at this computer ("DNS rebinding")
#   can't get in either.
# A tool that isn't a browser (the tests, curl) sends neither header and is
# let through: a website can't make a browser leave them out.

# Where a request may come from: Buddy's own page, or an address she typed.
OWN_PAGE = {"same-origin", "none"}


def host_name(host: str) -> str:
    """ "localhost:8000" -> "localhost", "[::1]:8000" -> "::1". """
    if host.startswith("["):
        return host[1:].split("]")[0]
    return host.split(":")[0].lower()


def allowed_host(host: str, allowed: tuple[str, ...]) -> bool:
    return host_name(host) in allowed


def from_buddys_page(headers, own_origin: str) -> bool:
    """True when the browser says this request comes from Buddy's own page
    (or says nothing, as a tool that isn't a browser does)."""
    site = headers.get("sec-fetch-site")
    if site is not None and site not in OWN_PAGE:
        return False
    origin = headers.get("origin")
    return origin is None or origin == own_origin
