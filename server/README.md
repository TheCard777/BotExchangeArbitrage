# Plateforme (backend) — faire tourner le bot pour plusieurs utilisateurs

Ce dossier `server/` transforme le bot en **plateforme** : des utilisateurs
créent un compte, connectent leurs **propres clés API** d'exchange, et le bot
scanne les opportunités d'arbitrage pour chacun d'eux, côté serveur.

> ⚠️ **À lire avant tout.** Héberger les clés API de tes utilisateurs est la
> partie la **plus sensible** possible : si ton serveur est piraté, ce sont
> les fonds de tes utilisateurs qui sont en jeu. Cette version est une
> **fondation (Phase 1)**, pas un produit fini prêt pour de l'argent réel.
> Lis la section « Sécurité & responsabilités » plus bas.

---

## Ce que ça fait déjà

- **Comptes** : inscription / connexion (mot de passe hashé PBKDF2, jamais en clair).
- **Clés API chiffrées** : chaque clé/secret/passphrase est chiffré (Fernet)
  avant d'être stocké. La base ne contient **jamais** de clé en clair.
- **Un bot par utilisateur** : chaque compte a son moteur qui scanne les
  opportunités avec **ses** exchanges.
- **Réglages par utilisateur** : paires, seuil de profit, taille max, top movers.
- **Mode démonstration par défaut** (`dry_run = true`) : aucun ordre réel tant
  que l'utilisateur n'active pas explicitement le mode réel.
- **API REST** (JSON) + une **page web** (tableau de bord) servie sur `/` :
  inscription/connexion, ajout des clés, réglages, démarrer/arrêter le bot et
  voir les opportunités en direct — sans écrire une ligne de code.

## Ce que ça ne fait PAS encore (volontairement)

- Pas de facturation / abonnements.
- Pas d'exécution d'ordres réels multi-utilisateurs durcie (le scan tourne ;
  l'activation du trading réel à grande échelle demande l'audit ci-dessous).
- Pas d'e-mails, reset de mot de passe, 2FA, limitation de débit.

---

## Lancer en local (pour tester)

```bash
# 1) dépendances du serveur (en plus de requirements.txt du bot)
pip install -r server/requirements.txt

# 2) génère UNE FOIS une clé maître de chiffrement et garde-la secrète
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# 3) mets-la dans l'environnement (ne la commit JAMAIS)
export BOT_PLATFORM_SECRET="colle_la_cle_ici"

# 4) démarre le serveur
uvicorn "server.app:get_app" --factory --reload
```

Ouvre ensuite **http://127.0.0.1:8000/** → la page web (inscription, connexion,
clés, réglages, démarrer/arrêter le bot).
Docs interactives de l'API : http://127.0.0.1:8000/docs

### Exemple d'utilisation (curl)

```bash
BASE=http://127.0.0.1:8000

# créer un compte + se connecter
curl -s $BASE/api/register -H 'Content-Type: application/json' \
     -d '{"email":"moi@exemple.com","password":"motdepasse123"}'
TOKEN=$(curl -s $BASE/api/login -H 'Content-Type: application/json' \
     -d '{"email":"moi@exemple.com","password":"motdepasse123"}' | python -c "import sys,json;print(json.load(sys.stdin)['token'])")

# connecter 2 exchanges (clés en trading seul, JAMAIS retrait)
curl -s -X PUT $BASE/api/exchanges/binance -H "Authorization: Bearer $TOKEN" \
     -H 'Content-Type: application/json' -d '{"api_key":"...","secret":"..."}'
curl -s -X PUT $BASE/api/exchanges/kraken -H "Authorization: Bearer $TOKEN" \
     -H 'Content-Type: application/json' -d '{"api_key":"...","secret":"..."}'

# lancer le bot et lire son état
curl -s -X POST $BASE/api/bot/start -H "Authorization: Bearer $TOKEN"
curl -s $BASE/api/bot/status -H "Authorization: Bearer $TOKEN"
```

---

## API en bref

| Méthode | Route | Auth | Rôle |
|--------|-------|------|------|
| POST | `/api/register` | non | créer un compte `{email, password}` (mdp ≥ 8) |
| POST | `/api/login` | non | obtenir un token `{token}` |
| POST | `/api/logout` | oui | invalider le token |
| GET | `/api/exchanges` | oui | lister ses exchanges (sans secrets) |
| PUT | `/api/exchanges/{ex}` | oui | ajouter/mettre à jour une clé `{api_key, secret, passphrase?}` |
| DELETE | `/api/exchanges/{ex}` | oui | supprimer une clé |
| GET | `/api/config` | oui | lire ses réglages |
| PUT | `/api/config` | oui | modifier `{dry_run, pairs, min_profit_threshold, max_trade_size_quote, top_movers}` |
| POST | `/api/bot/start` | oui | démarrer son bot (≥ 2 exchanges requis) |
| POST | `/api/bot/stop` | oui | arrêter son bot |
| GET | `/api/bot/status` | oui | état + opportunités + résumé |

Authentification : en-tête `Authorization: Bearer <token>`.

---

## Architecture

```
server/
  crypto_box.py   chiffrement Fernet des clés (BOT_PLATFORM_SECRET)
  security.py     hash de mot de passe (PBKDF2) + tokens de session
  store.py        SQLite : users, sessions, clés chiffrées, config
  engine.py       UserBotEngine (1 par user) + BotManager, réutilise bot/
  app.py          API FastAPI qui relie le tout
```

Le moteur **réutilise le code du bot** (`bot/scanner.py`, `bot/exchange_client.py`,
`bot/dns_fallback.py`) — pas de duplication de la logique d'arbitrage.

---

## Sécurité & responsabilités (lis-le vraiment)

1. **La clé maître (`BOT_PLATFORM_SECRET`) protège tout.** Si elle fuite en même
   temps que la base, toutes les clés API sont déchiffrables. En production :
   gestionnaire de secrets (Vault, AWS/GCP Secrets Manager), **jamais** dans le
   code ni dans git. La perdre = clés irrécupérables.
2. **Clés en trading seul, JAMAIS retrait.** Impose à tes utilisateurs des clés
   API sans droit de retrait (voir `GUIDE_API.md`). C'est ta principale
   protection si un compte est compromis.
3. **HTTPS obligatoire** en production (les tokens et clés transitent en clair
   sinon). Mets un reverse-proxy TLS (Caddy, Nginx) devant uvicorn.
4. **Manque encore pour la prod** : limitation de débit (anti brute-force),
   expiration des sessions, 2FA, journaux d'audit, sauvegardes chiffrées,
   isolation des processus par utilisateur, surveillance.
5. **Poids juridique.** Gérer les clés/fonds d'autrui et « trader à leur place »
   peut relever de la réglementation financière (selon les pays). Fais-toi
   conseiller juridiquement avant d'ouvrir ça au public ou de facturer. Prévois
   des CGU, une politique de confidentialité et des avertissements de risque
   clairs. **Le trading crypto peut faire perdre de l'argent.**

En résumé : la fondation technique est là et testée, mais **n'ouvre pas ça à de
vrais utilisateurs avec de l'argent réel** sans le durcissement et l'avis
juridique ci-dessus.
