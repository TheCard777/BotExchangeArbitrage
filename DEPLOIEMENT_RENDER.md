# Mettre la plateforme en ligne sur Render.com

Ce guide met **toute la plateforme** (interface web + bot) en ligne, avec une
vraie adresse `https://...` accessible par tes clients. Compte ~15 minutes.

> Le fichier `render.yaml` (déjà dans le dépôt) configure presque tout
> automatiquement. Tu n'as quasiment que des boutons à cliquer.

---

## Avant de commencer

- Un compte **GitHub** avec ce dépôt (déjà le cas).
- Un compte **Render** gratuit : https://render.com (connecte-toi avec GitHub).

---

## Étape 1 — Générer ta clé maître de chiffrement

Sur ton PC (cmd Windows), lance :

```cmd
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

👉 **Copie la ligne affichée** (ex. `gAAAAAB...=`) et garde-la de côté pour
l'étape 3. C'est elle qui protège les clés API de tes utilisateurs.
**Ne la mets jamais dans le code ni sur GitHub.**

---

## Étape 2 — Créer le service sur Render

1. Va sur https://dashboard.render.com → **New +** → **Blueprint**.
2. Choisis ce dépôt GitHub (autorise Render à y accéder si demandé).
3. Sélectionne la **branche** `claude/crypto-arbitrage-bot-mfh73q`
   (ou `main` si tu as fusionné).
4. Render détecte le fichier **`render.yaml`** et propose de créer le service
   **plateforme-arbitrage**. Clique **Apply** / **Create**.

---

## Étape 3 — Coller la clé secrète

Render va te demander la valeur de **`BOT_PLATFORM_SECRET`** (parce qu'elle
n'est volontairement pas dans le code).

- Colle la clé copiée à l'**étape 1**.
- Valide.

> Si Render ne la demande pas pendant la création : va dans le service →
> onglet **Environment** → **Add Environment Variable** →
> clé `BOT_PLATFORM_SECRET`, valeur = ta clé → **Save**.

---

## Étape 4 — Attendre le déploiement, puis ouvrir

- Render installe tout (2–5 min). Regarde l'onglet **Logs** : quand tu vois
  `Uvicorn running` / `Application startup complete`, c'est bon.
- En haut de la page du service, Render affiche l'adresse, du style :
  **`https://plateforme-arbitrage.onrender.com`**
- Ouvre-la : tu tombes sur ta page de connexion. **C'est cette adresse que tu
  donnes à tes clients.** 🎉

---

## ⚠️ Limites de l'offre GRATUITE (à connaître)

L'offre gratuite est parfaite pour **tester**, mais :

1. **Le service s'endort après ~15 min sans visite.** Il se réveille à la
   visite suivante (30–60 s de latence). Pendant qu'il dort, **le bot ne scanne
   pas**. Pour un bot qui doit tourner en continu → offre payante (« Starter »).
2. **La base de données est effacée à chaque redémarrage/déploiement.** Donc les
   comptes et clés enregistrés sont **perdus**. Pour les garder :
   - passe en offre payante,
   - dans `render.yaml`, **décommente le bloc `disk:`** (en bas),
   - change `PLATFORM_DB_PATH` en `"/var/data/platform.db"`,
   - commit + push : Render redéploie avec un disque permanent.

En résumé : **gratuit = démo**. Pour de vrais clients qui reviennent, prévois
l'offre payante + le disque permanent.

---

## 🔒 Sécurité & juridique (ne saute pas ça)

Avant d'ouvrir à de vrais utilisateurs avec de l'argent réel :

- **HTTPS** : Render le fournit automatiquement ✅ (bon point).
- **Clés API trading-seul, jamais retrait** : impose-le à tes clients
  (voir `GUIDE_API.md`). C'est ta protection principale.
- **Manque encore** pour la prod : limitation anti-brute-force, expiration des
  sessions, 2FA, sauvegardes chiffrées de la base. Ce sont des ajouts à prévoir.
- **La clé `BOT_PLATFORM_SECRET` est vitale** : si tu la perds, toutes les clés
  API enregistrées deviennent illisibles. Sauvegarde-la dans un endroit sûr
  (gestionnaire de mots de passe).
- **Poids juridique** : gérer les clés/fonds d'autrui et « trader à leur place »
  peut relever de la réglementation financière selon les pays. Fais-toi
  conseiller avant d'ouvrir au public ou de facturer (CGU, confidentialité,
  avertissement de risque). **Le trading crypto peut faire perdre de l'argent.**

---

## Problèmes fréquents

| Symptôme | Cause probable / solution |
|----------|---------------------------|
| Page « Application error » | `BOT_PLATFORM_SECRET` non défini → étape 3. |
| Le build échoue | Regarde les **Logs** ; souvent une dépendance. Réessaie « Manual Deploy ». |
| Lent à la première visite | Normal en gratuit (le service se réveille). |
| Les comptes disparaissent | Base éphémère en gratuit → disque permanent (voir limites). |

Tout le reste (comment le bot trade, la gestion des fonds, les risques) est dans
**GUIDE.md** et **server/README.md**.
