# Guide : créer ses clés API (pour le trading réel)

Ce guide explique comment créer une clé API sur chaque exchange, pour que le
bot puisse trader à ta place. À faire **uniquement quand tu veux passer en
mode réel**. En mode démonstration, tu n'as besoin d'aucune clé.

---

## Règle de sécurité n°1 (à respecter partout)

Quand tu crées une clé API, tu choisis ses **permissions**. Pour ce bot :

- ✅ **Autorise le TRADING** (achat/vente au comptant / "Spot").
- ❌ **N'autorise JAMAIS le RETRAIT / WITHDRAWAL.**

Comme ça, même si ta clé était volée, personne ne pourrait **sortir** ton
argent de l'exchange. Le bot n'a pas besoin du droit de retrait pour
fonctionner.

Ne partage jamais ta clé, ton secret (ni ta passphrase). Le secret n'est
souvent affiché **qu'une seule fois** à la création : copie-le tout de suite.

> 💡 **Conseil débutant :** commence avec **Binance + Kraken**. Ce sont les
> plus simples (clé + secret, pas de passphrase).

---

## Ce que le bot te demandera

Quand tu relances `./install.sh` et choisis le mode réel, il te demande, pour
chaque exchange :

- la **clé API** (API Key),
- le **secret** (API Secret / Private Key),
- et, **pour KuCoin et OKX uniquement**, une **passphrase** (que tu choisis
  toi-même au moment de créer la clé sur l'exchange).

---

## Binance

1. Connecte-toi, va dans **Profil → Gestion des API** (Account → API Management).
2. Clique **Créer une API** → choisis **"Généré par le système"** (System generated).
3. Donne un nom (ex. `bot`), valide avec ta double authentification (2FA).
4. Copie l'**API Key** et la **Secret Key** (le secret n'apparaît qu'une fois).
5. Clique **Modifier les restrictions** et coche **uniquement** :
   - ✅ *Enable Spot & Margin Trading*
   - ❌ laisse *Enable Withdrawals* **décoché**.
6. Enregistre.

Le bot te demandera : `BINANCE_API_KEY` et `BINANCE_API_SECRET`.

---

## Kraken

1. Va dans **Paramètres → API** (Settings → API) → **Ajouter une clé API**.
2. Coche exactement ces autorisations :
   - Colonne **Fonds** : ✅ **Requête** (lire les soldes).
   - Colonne **Ordres et transactions** :
     ✅ **Créer et modifier des ordres** (passer les trades),
     ✅ **Consulter les ordres et transactions ouverts** *(recommandé)*,
     ✅ **Consulter les ordres et les transactions clôturés** *(recommandé)*.
   - ❌ **NE coche PAS** *Retrait*, *Dépôt*, *Gains*.
3. Laisse les 3 interrupteurs du bas sur **Désactivé** :
   - **Interface WebSocket** : Désactivé (le bot utilise le flux public, pas
     besoin de cette option).
   - **Restriction d'adresse IP** : Désactivé (une restriction d'IP est une
     cause fréquente de clé qui « ne marche pas »).
   - **Expiration de la clé** : Désactivé (pour qu'elle ne se périme pas).
4. Nomme-la (ex. `bot`), génère, et copie la **Key** et la **Private Key**.

Le bot te demandera : `KRAKEN_API_KEY` (= la Key) et `KRAKEN_API_SECRET`
(= la Private Key).

---

## Bybit

1. Va dans **Compte → API** (API Management) → **Créer une nouvelle clé**
   (**System-generated API Keys**).
2. ⚠️ **LE POINT LE PLUS IMPORTANT** — « Autorisations de la clé API » :
   choisis **« Lecture-écriture »** (Read-Write).
   - ❌ **PAS « Lecture seule »** (Read-only) ! Une clé en lecture seule ne peut
     que regarder, pas trader → le bot la refuse (« permissions insuffisantes »).
3. Coche **Trader** sous **SPOT / Trading Unifié** (le droit de passer des ordres).
   - ❌ ne coche PAS Retrait ni Transfert de compte.
4. **Restriction d'adresse IP** : laisse **aucune** (ou ajoute ton IP). Une
   restriction d'IP mal réglée fait aussi rejeter la clé.
5. **Envoyer**, puis copie la **clé** et le **secret**.

Le bot te demandera : `BYBIT_API_KEY` et `BYBIT_API_SECRET`.

---

## Coinbase

1. Va dans les **paramètres API** de ton compte Coinbase (section API / API keys).
2. Crée une nouvelle clé avec la permission de **trade** (acheter/vendre).
   - ❌ pas de permission de transfert/retrait.
3. Copie la **clé** et le **secret**.

Le bot te demandera : `COINBASE_API_KEY` et `COINBASE_API_SECRET`.

> Note : selon le type de compte, Coinbase propose plusieurs systèmes de clés.
> Choisis celui qui donne un **API Key + Secret** avec droit de trading.

---

## KuCoin  ⚠️ (passphrase requise)

1. Va dans **Gestion des API** (API Management) → **Créer une API**.
2. Choisis **API-based** (clé classique).
3. **Choisis toi-même une passphrase** et **note-la** : le bot la demandera.
4. Permissions : coche **General** et **Trade** (Spot).
   - ❌ ne coche PAS *Transfer* ni *Withdrawal*.
5. Valide avec ta 2FA, copie la **clé** et le **secret**.

Le bot te demandera : `KUCOIN_API_KEY`, `KUCOIN_API_SECRET` **et**
`KUCOIN_API_PASSPHRASE` (celle que tu as choisie à l'étape 3).

---

## OKX  ⚠️ (passphrase requise)

1. Va dans **Profil → API** → **Créer une clé API** (V5).
2. **Choisis une passphrase** et **note-la** : le bot la demandera.
3. Permissions : coche **Trade**.
   - ❌ ne coche PAS *Withdraw*.
4. Copie la **clé** et le **secret**.

Le bot te demandera : `OKX_API_KEY`, `OKX_API_SECRET` **et**
`OKX_API_PASSPHRASE`.

---

## Bitget  ⚠️ (passphrase requise)

1. Va dans **API Management** (Gestion des API) → **Créer une clé API**.
2. **Choisis une passphrase** et **note-la** : le bot la demandera.
3. Permissions : coche **Trading (Spot)** en lecture + trade.
   - ❌ ne coche PAS *Withdraw* (retrait).
4. Copie la **clé** et le **secret**.

Le bot te demandera : `BITGET_API_KEY`, `BITGET_API_SECRET` **et**
`BITGET_API_PASSPHRASE`.

---

## Autres exchanges (Gate.io, MEXC, HTX, Bitfinex, Crypto.com, BingX)

Même principe pour tous : dans les paramètres API de l'exchange, crée une clé
avec **le droit de trading (spot)**, **sans droit de retrait**, et **sans
restriction d'IP** (sinon la clé peut être rejetée). Ces exchanges n'utilisent
que **clé + secret** (pas de passphrase). Le bot demandera
`NOM_API_KEY` / `NOM_API_SECRET` (ex. `GATE_API_KEY`, `MEXC_API_KEY`...).

La règle de sécurité est toujours la même : **trading oui, retrait jamais**.

---

## Après avoir créé tes clés

1. Relance **`./install.sh`**.
2. Choisis l'option **"Oui, je veux configurer mes cles pour trader"**.
3. Colle, pour chaque exchange, la clé, le secret (et la passphrase pour
   KuCoin/OKX/Bitget). La saisie est **masquée** à l'écran, c'est normal.
4. Indique ton **montant maximum par trade** (commence petit : 20-50 USDT).
5. Tape **`ACTIVER`** à la dernière question pour lancer le mode réel
   (ou Entrée pour rester en démonstration).
6. Lance **`./start.sh`**.

Tu peux à tout moment revérifier ou refaire cette étape en relançant
`./install.sh`. Le reste (comment le bot trade, la gestion des fonds sur les
deux exchanges, les risques) est expliqué dans **GUIDE.md**.
