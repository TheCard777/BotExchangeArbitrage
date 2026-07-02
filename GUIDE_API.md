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

1. Va dans **Paramètres → API** (Settings → API).
2. Clique **Créer une clé** (Add key / Create API key).
3. Coche les permissions :
   - ✅ *Query Funds* (consulter les soldes)
   - ✅ *Create & Modify Orders* (passer des ordres)
   - ✅ *Query Open/Closed Orders & Trades*
   - ❌ **NE coche PAS** *Withdraw Funds*.
4. Génère la clé et copie la **Key** et la **Private Key**.

Le bot te demandera : `KRAKEN_API_KEY` et `KRAKEN_API_SECRET`.

---

## Bybit

1. Va dans **Compte → API** (API Management) → **Créer une nouvelle clé**.
2. Choisis **"System-generated API Keys"**.
3. Type : **Read-Write**. Permissions : coche **Spot Trading** (ordres).
   - ❌ ne coche pas les retraits.
4. Copie la **clé** et le **secret**.

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

## Après avoir créé tes clés

1. Relance **`./install.sh`**.
2. Choisis l'option **"Oui, je veux configurer mes cles pour trader"**.
3. Colle, pour chaque exchange, la clé, le secret (et la passphrase pour
   KuCoin/OKX). La saisie est **masquée** à l'écran, c'est normal.
4. Indique ton **montant maximum par trade** (commence petit : 20-50 USDT).
5. Tape **`ACTIVER`** à la dernière question pour lancer le mode réel
   (ou Entrée pour rester en démonstration).
6. Lance **`./start.sh`**.

Tu peux à tout moment revérifier ou refaire cette étape en relançant
`./install.sh`. Le reste (comment le bot trade, la gestion des fonds sur les
deux exchanges, les risques) est expliqué dans **GUIDE.md**.
