# MyBestSim Analytics Dashboard

Plateforme de Business Intelligence pour explorer et analyser le catalogue eSIM MyBestSim. L'application est construite avec **Python**, **Streamlit**, **Pandas**, **Plotly** et **PostgreSQL/Supabase**.

## Fonctionnalités

- **Vue d'ensemble** : indicateurs de catalogue, répartition par fournisseur et destination, distribution des prix.
- **Filtres combinés** : fournisseur, pays/territoire, réseau, devise, année de première observation, recharge et type de forfait.
- **Recherche** : recherche textuelle dans le catalogue.
- **Catalogue détaillé** : tri croissant/décroissant et export des résultats filtrés en CSV.
- **Qualité des données** : complétude de champs clés, valeurs manquantes, doublons potentiels, prix négatifs et durées invalides.
- **Gestion des CSV** : validation avant import, ajout ou mise à jour d'un dataset, désactivation réversible et suppression définitive.
- **Actualisation après import** : après un import réussi, les caches sont invalidés pour recharger les données et recalculer les indicateurs.

> Les contrôles de qualité signalent les éléments à examiner ; ils ne remplacent pas la validation métier. Un volume numérique manquant, par exemple, peut être légitime pour un forfait illimité.

## Architecture

```text
CSV fournisseur
     |
     v
Validation du fichier
     |
     v
Application Streamlit
     |
     v
PostgreSQL / Supabase
     |
     v
Requêtes SQL -> Pandas -> KPI et graphiques Plotly
```

Les fichiers CSV et les identifiants de connexion ne doivent pas être stockés dans ce dépôt. Les données sont lues et écrites dans Supabase.

## Structure du projet

```text
mybestsim-analytics-dashboard/
├── app.py
├── requirements.txt
├── mybestsim_logo.png
├── .env.example
├── .gitignore
└── README.md
```

## Prérequis

- Python 3.10 ou une version compatible avec les dépendances du projet.
- Un projet Supabase/PostgreSQL configuré avec le schéma attendu par l'application.
- Une chaîne de connexion PostgreSQL valide.
- Un mot de passe administrateur pour activer la gestion des CSV.

Les tables principales attendues par le dashboard sont `providers`, `datasets` et `products`. L'historique d'import utilise la table `import_runs` lorsqu'elle est disponible. Les noms et colonnes doivent correspondre au schéma de la base de données utilisée.

## Lancer l'application en local

### 1. Cloner le dépôt

```bash
git clone https://github.com/<OWNER>/mybestsim-analytics-dashboard.git
cd mybestsim-analytics-dashboard
```

Remplacez `<OWNER>` par le nom du compte ou de l'organisation GitHub.

### 2. Créer un environnement virtuel (recommandé)

Windows PowerShell :

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

macOS / Linux :

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Installer les dépendances

```bash
python -m pip install -r requirements.txt
```

### 4. Configurer les secrets locaux

Copiez `.env.example` vers `.env`, puis renseignez vos propres valeurs :

```text
DATABASE_URL="VOTRE_CHAINE_DE_CONNEXION_SUPABASE"
ADMIN_PASSWORD="UN_MOT_DE_PASSE_LONG_ET_UNIQUE"
```

Le fichier `.env` est local et ne doit jamais être commité. Ne collez jamais vos identifiants réels dans le code, dans le README ou dans une issue publique.

### 5. Démarrer Streamlit

```bash
python -m streamlit run app.py
```

L'application est normalement accessible à l'adresse `http://localhost:8501`.
