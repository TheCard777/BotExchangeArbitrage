"""Plain-language classification of exchange connection failures.

Turns a raw ccxt/network exception into a category + a clear French message,
so both the running bot and the standalone diagnose.py tool can tell the user
*why* an exchange is unreachable (geo-block, slow link, firewall, keys...)
instead of dumping a cryptic stack trace.
"""
from __future__ import annotations

# (category, message) — category is a stable key for code, message is shown.
GEOBLOCK = "geoblock"
BLOCKED = "blocked"
TIMEOUT = "timeout"
NETWORK = "network"
MAINTENANCE = "maintenance"
AUTH = "auth"
UNKNOWN = "unknown"

_GEOBLOCK_HINTS = (
    "451",
    "restricted location",
    "unavailable for legal",
    "eligibility",
    "restricted jurisdiction",
    "not available in your",
    "service unavailable from a restricted",
)
_TIMEOUT_HINTS = ("timeout", "timed out", "request timeout")
_NETWORK_HINTS = (
    "name or service not known",
    "cannot connect",
    "getaddrinfo",
    "temporary failure in name",
    "connection refused",
    "network is unreachable",
    "ssl",
    "certificate",
    "connection reset",
    "connection aborted",
)
_MAINTENANCE_HINTS = ("maintenance", "system maintenance")
_AUTH_HINTS = ("invalid api", "authentication", "api-key", "apikey", "signature", "permission denied")


def classify_error(exc: BaseException) -> tuple[str, str]:
    """Return (category, human-readable French message) for a connection error."""
    text = f"{type(exc).__name__}: {exc}".lower()
    # ccxt exception class names along the inheritance chain are themselves a
    # strong signal even when the message has no recognizable keyword.
    type_names = {cls.__name__.lower() for cls in type(exc).__mro__}

    if any(h in text for h in _GEOBLOCK_HINTS):
        return GEOBLOCK, (
            "L'exchange refuse les connexions depuis ce pays/region (restriction legale, "
            "code 451). Aucun reglage du bot ne peut contourner ca : il faut un VPN vers un "
            "pays autorise, ou remplacer cet exchange par un autre disponible dans ta region."
        )
    if any(h in text for h in _TIMEOUT_HINTS):
        return TIMEOUT, (
            "Delai depasse : la connexion est trop lente ou instable pour cet exchange. "
            "Augmente request_timeout_seconds dans config.yaml (ex: 60) ou change de reseau."
        )
    if "403" in text or "forbidden" in text:
        return BLOCKED, (
            "Acces refuse (403) : ton reseau, ton operateur ou un pare-feu bloque cet exchange "
            "(ou restriction geographique). Essaie un autre reseau (Wi-Fi/4G) ou un VPN."
        )
    if any(h in text for h in _NETWORK_HINTS):
        return NETWORK, (
            "Impossible d'atteindre le serveur (DNS/reseau/pare-feu). Verifie ta connexion, "
            "coupe un eventuel VPN/proxy, ou essaie un autre reseau."
        )
    if any(h in text for h in _MAINTENANCE_HINTS):
        return MAINTENANCE, "L'exchange est en maintenance. Reessaie plus tard."
    if any(h in text for h in _AUTH_HINTS):
        return AUTH, (
            "Probleme de cles API (cle/secret invalide ou droits insuffisants). "
            "Verifie tes cles, ou reste en mode demonstration qui n'en a pas besoin."
        )

    # No keyword matched — fall back to the exception type. ccxt names are:
    # RequestTimeout, OnMaintenance, AuthenticationError/PermissionDenied,
    # DDoSProtection, ExchangeNotAvailable, and the NetworkError base class.
    if "requesttimeout" in type_names:
        return TIMEOUT, (
            "Delai depasse : la connexion est trop lente ou instable pour cet exchange. "
            "Augmente request_timeout_seconds dans config.yaml (ex: 60) ou change de reseau."
        )
    if "onmaintenance" in type_names:
        return MAINTENANCE, "L'exchange est en maintenance. Reessaie plus tard."
    if {"authenticationerror", "permissiondenied"} & type_names:
        return AUTH, (
            "Probleme de cles API (cle/secret invalide ou droits insuffisants). "
            "Verifie tes cles, ou reste en mode demonstration qui n'en a pas besoin."
        )
    if "ddosprotection" in type_names:
        return BLOCKED, (
            "L'exchange a refuse la connexion (protection anti-abus / trop de requetes, "
            "souvent lie a l'IP ou au reseau). Essaie un autre reseau ou un VPN."
        )
    if "exchangenotavailable" in type_names:
        return NETWORK, (
            "L'exchange ne repond pas correctement : indisponible, bloque par le reseau, "
            "ou non accessible depuis ta region. Essaie un autre reseau (Wi-Fi/4G) ou un VPN ; "
            "si ca persiste, remplace cet exchange par un autre dans config.yaml."
        )
    if "networkerror" in type_names:
        return NETWORK, (
            "Impossible d'atteindre le serveur (reseau/pare-feu). Verifie ta connexion, "
            "coupe un eventuel VPN/proxy, ou essaie un autre reseau."
        )
    return UNKNOWN, f"Erreur inattendue : {type(exc).__name__}: {exc}"
