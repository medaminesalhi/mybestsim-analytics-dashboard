import os
import io
import hmac
import re
import json
import hashlib
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

from dotenv import load_dotenv
from sqlalchemy import (
    Boolean, MetaData, Table, create_engine, text,
    select, insert, update, delete, func, inspect,
)
from sqlalchemy.engine import make_url


# ============================================================
# MYBESTSIM ANALYTICS — ONE-PAGE PROFESSIONAL DASHBOARD
# Stack: Streamlit + PostgreSQL/Supabase + Pandas + Plotly
# ============================================================

st.set_page_config(
    page_title="MyBestSim | Analytics",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


# --------------------------- Theme ---------------------------

st.markdown(
    """
    <style>
    :root {
        --blue: #079FE3;
        --blue-dark: #087EB8;
        --blue-pale: #EAF7FF;
        --navy: #111D35;
        --muted: #657A91;
        --border: #DDECF5;
        --surface: #FFFFFF;
        --teal: #12B8A6;
    }

    .stApp {
        background: linear-gradient(180deg, #F1FAFF 0%, #FFFFFF 38%, #F7FBFE 100%);
        color: var(--navy);
    }

    .block-container {
        max-width: 1580px;
        padding-top: 1.5rem;
        padding-bottom: 3rem;
    }

    section[data-testid="stSidebar"] {
        background: #F0F9FF;
        border-right: 1px solid var(--border);
    }

    section[data-testid="stSidebar"] hr {
        border-color: #D6EAF6;
    }

    .hero {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 20px;
        padding: 24px 28px;
        margin-bottom: 22px;
        background: linear-gradient(115deg, #FFFFFF 0%, #EAF7FF 100%);
        border: 1px solid var(--border);
        border-top: 4px solid var(--blue);
        border-radius: 18px;
        box-shadow: 0 8px 28px rgba(24, 100, 145, 0.055);
    }

    .hero-eyebrow {
        font-size: 0.70rem;
        font-weight: 800;
        letter-spacing: 1.8px;
        color: var(--blue-dark);
        margin-bottom: 8px;
    }

    .hero-title {
        color: var(--navy);
        font-size: clamp(1.65rem, 2.8vw, 2.35rem);
        font-weight: 850;
        letter-spacing: -1px;
        line-height: 1.15;
        margin: 0;
    }

    .hero-subtitle {
        color: var(--muted);
        font-size: 0.96rem;
        margin-top: 9px;
    }

    .hero-chip {
        display: inline-block;
        white-space: nowrap;
        background: #FFFFFF;
        color: #087EB8;
        border: 1px solid #C7E8F8;
        border-radius: 999px;
        padding: 9px 13px;
        font-size: 0.78rem;
        font-weight: 750;
    }

    .section-kicker {
        color: #087EB8;
        font-size: 0.73rem;
        font-weight: 800;
        letter-spacing: 1.5px;
        text-transform: uppercase;
        margin-bottom: 3px;
    }

    .section-note {
        color: var(--muted);
        font-size: 0.90rem;
        margin-bottom: 14px;
    }

    div[data-testid="stMetric"] {
        background: #FFFFFF;
        border: 1px solid var(--border);
        border-radius: 15px;
        padding: 17px 19px;
        box-shadow: 0 5px 20px rgba(23, 91, 135, 0.045);
    }

    div[data-testid="stMetricLabel"] {
        color: var(--muted);
        font-size: 0.83rem;
    }

    div[data-testid="stMetricValue"] {
        color: var(--navy);
        font-weight: 800;
    }

    div[data-testid="stPlotlyChart"] {
        background: #FFFFFF;
        border: 1px solid var(--border);
        border-radius: 14px;
        padding: 7px;
        box-shadow: 0 5px 20px rgba(23, 91, 135, 0.035);
    }

    div[data-testid="stDataFrame"] {
        background: #FFFFFF;
        border: 1px solid var(--border);
        border-radius: 12px;
        overflow: hidden;
    }

    div[data-baseweb="select"] > div,
    div[data-baseweb="input"] > div {
        border-color: #CFE3F0;
        border-radius: 9px;
        background: #FFFFFF;
    }

    .stButton > button,
    .stDownloadButton > button {
        border-radius: 9px;
        font-weight: 650;
    }

    .stButton > button[kind="primary"] {
        background: var(--blue);
        border-color: var(--blue);
        color: #FFFFFF;
    }

    .stButton > button[kind="primary"]:hover {
        background: var(--blue-dark);
        border-color: var(--blue-dark);
    }

    .status-note {
        background: #FFFFFF;
        border: 1px solid var(--border);
        border-radius: 12px;
        padding: 13px 16px;
        color: var(--muted);
        font-size: 0.88rem;
    }

    @media (max-width: 768px) {
        .block-container {
            padding: 1rem 0.8rem 2rem;
        }
        .hero {
            padding: 18px;
            flex-direction: column;
            align-items: flex-start;
        }
    }
    </style>
    """,
    unsafe_allow_html=True,
)

px.defaults.template = "plotly_white"
px.defaults.color_discrete_sequence = [
    "#079FE3",
    "#12B8A6",
    "#637CE8",
    "#F5A623",
    "#EF6B73",
]


# ----------------------- Configuration -----------------------

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "").strip()


def make_engine(database_url: str):
    """Create a SQLAlchemy engine for the Supabase PostgreSQL URL."""
    url = make_url(database_url)
    if url.drivername in ("postgresql", "postgres"):
        url = url.set(drivername="postgresql+psycopg")

    return create_engine(
        url,
        connect_args={
            "sslmode": "require",
            "connect_timeout": 10,
        },
        pool_pre_ping=True,
    )


@st.cache_resource
def get_engine(database_url: str):
    return make_engine(database_url)


# -------------------------- Data layer ------------------------

@st.cache_data(ttl=60, show_spinner="Chargement du catalogue...")
def load_products(database_url: str) -> pd.DataFrame:
    engine = get_engine(database_url)

    query = text(
        """
        SELECT
            p.id,
            p.dataset_id,
            p.sku,
            p.product_name,
            p.country_code,
            p.country_name,
            p.data_gb,
            p.data_display,
            p.validity_days,
            p.price,
            p.currency,
            p.network,
            p.top_up,
            p.first_seen_at,
            p.last_seen_at,
            d.filename,
            pr.name AS provider
        FROM products AS p
        JOIN datasets AS d
            ON d.id = p.dataset_id
        JOIN providers AS pr
            ON pr.id = d.provider_id
        WHERE d.status = 'active'
          AND p.is_active = TRUE
        ORDER BY p.product_name
        """
    )

    with engine.connect() as connection:
        df = pd.read_sql_query(query, connection)

    for column in ("price", "data_gb", "validity_days"):
        df[column] = pd.to_numeric(df[column], errors="coerce")

    for column in ("first_seen_at", "last_seen_at"):
        if column in df.columns:
            df[column] = pd.to_datetime(df[column], errors="coerce", utc=True)

    for column in (
        "sku", "product_name", "country_code", "country_name",
        "data_display", "currency", "network", "filename", "provider",
    ):
        if column in df.columns:
            df[column] = df[column].astype("string")

    return df


@st.cache_data(ttl=60, show_spinner=False)
def load_datasets(database_url: str) -> pd.DataFrame:
    engine = get_engine(database_url)

    query = text(
        """
        SELECT
            d.id,
            d.filename,
            pr.name AS provider,
            d.status,
            d.expected,
            d.last_row_count,
            d.last_imported_at
        FROM datasets AS d
        JOIN providers AS pr
            ON pr.id = d.provider_id
        ORDER BY d.filename
        """
    )

    with engine.connect() as connection:
        return pd.read_sql_query(query, connection)


@st.cache_data(ttl=60, show_spinner=False)
def load_import_history(database_url: str) -> pd.DataFrame:
    engine = get_engine(database_url)

    query = text(
        """
        SELECT
            r.started_at,
            d.filename,
            r.status,
            r.total_rows,
            r.inserted_rows,
            r.updated_rows,
            r.unchanged_rows,
            r.rejected_rows,
            r.error_message
        FROM import_runs AS r
        JOIN datasets AS d
            ON d.id = r.dataset_id
        ORDER BY r.started_at DESC
        LIMIT 100
        """
    )

    with engine.connect() as connection:
        return pd.read_sql_query(query, connection)


def clear_data_cache():
    load_products.clear()
    load_datasets.clear()
    load_import_history.clear()


# -------------------------- Helpers ---------------------------

def format_count(value) -> str:
    try:
        return f"{int(value):,}".replace(",", " ")
    except (ValueError, TypeError):
        return "—"


def format_money(value, currency) -> str:
    if pd.isna(value) or currency is None or pd.isna(currency):
        return "—"
    return f"{float(value):,.2f} {currency}".replace(",", " ")


def get_unlimited_mask(df: pd.DataFrame) -> pd.Series:
    text_values = df["data_display"].fillna("").astype(str)
    return text_values.str.contains(
        r"illimité|illimite|unlimited",
        case=False,
        regex=True,
    )


def normalize_top_up(series: pd.Series) -> pd.Series:
    values = series.astype("string").str.strip().str.lower()
    yes_values = {"true", "1", "yes", "oui", "y", "vrai"}
    no_values = {"false", "0", "no", "non", "n", "faux"}

    result = pd.Series(pd.NA, index=series.index, dtype="string")
    result.loc[values.isin(yes_values)] = "Oui"
    result.loc[values.isin(no_values)] = "Non"
    return result


def make_chart(fig, height=350):
    fig.update_layout(
        height=height,
        margin=dict(l=18, r=18, t=58, b=18),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(
            family="Arial, sans-serif",
            color="#344054",
            size=12,
        ),
        title=dict(
            x=0.02,
            xanchor="left",
            font=dict(size=16, color="#111D35"),
        ),
        legend_title_text="",
    )
    fig.update_xaxes(showgrid=True, gridcolor="#EAF0F5", zeroline=False)
    fig.update_yaxes(showgrid=True, gridcolor="#EAF0F5", zeroline=False)
    return fig


def page_heading(title, subtitle):
    st.markdown(
        f"""
        <div class="section-kicker">MYBESTSIM / ANALYTICS</div>
        <h2 style="color:#111D35; margin:0 0 4px 0; font-weight:800;">
            {title}
        </h2>
        <div class="section-note">{subtitle}</div>
        """,
        unsafe_allow_html=True,
    )


# --------------------------- Sidebar --------------------------

logo_path = BASE_DIR / "mybestsim_logo.png"

if logo_path.exists():
    st.sidebar.image(str(logo_path), width=92)
else:
    st.sidebar.markdown("## MyBestSim")

st.sidebar.markdown(
    """
    <div style="font-size:1.35rem;font-weight:850;color:#111D35;">
        MyBestSim
    </div>
    <div style="font-size:0.68rem;letter-spacing:1.5px;color:#648198;">
        DATA & ANALYTICS
    </div>
    """,
    unsafe_allow_html=True,
)

st.sidebar.divider()
st.sidebar.markdown("### Filtres globaux")
st.sidebar.caption("Les filtres s'appliquent aux KPI, graphiques et résultats.")

if st.sidebar.button("↻ Actualiser les données", use_container_width=True):
    clear_data_cache()
    st.rerun()


# ------------------------- Load data --------------------------

if not DATABASE_URL:
    st.error(
        "La variable DATABASE_URL est absente. "
        "Ajoute la chaîne de connexion Supabase dans le fichier .env."
    )
    st.code('DATABASE_URL="TA_CHAINE_DE_CONNEXION_SUPABASE"')
    st.stop()

try:
    products_all = load_products(DATABASE_URL)
except Exception as exc:
    st.error(
        "Impossible de lire la table des produits. "
        "Vérifie la connexion Supabase et les noms des tables/colonnes."
    )
    with st.expander("Détails techniques"):
        st.code(f"{type(exc).__name__}: {exc}")
    st.stop()

try:
    datasets_all = load_datasets(DATABASE_URL)
except Exception:
    datasets_all = pd.DataFrame(
        columns=[
            "id", "filename", "provider", "status",
            "expected", "last_row_count", "last_imported_at",
        ]
    )

if products_all.empty:
    st.warning(
        "La connexion fonctionne, mais aucun produit actif n'a été trouvé. "
        "Vérifie les statuts des datasets et des produits dans Supabase."
    )
    st.stop()


# ------------------------ Filter controls ---------------------

df = products_all.copy()

provider_options = sorted(df["provider"].dropna().astype(str).unique().tolist())
country_options = sorted(df["country_name"].dropna().astype(str).unique().tolist())
network_options = sorted(df["network"].dropna().astype(str).unique().tolist())
currency_options = sorted(df["currency"].dropna().astype(str).unique().tolist())

with st.sidebar:
    selected_providers = st.multiselect(
        "Fournisseur",
        options=provider_options,
        default=provider_options,
        help="Choisis un ou plusieurs fournisseurs.",
    )

    selected_countries = st.multiselect(
        "Pays / territoire",
        options=country_options,
        default=[],
    )

    selected_networks = st.multiselect(
        "Réseau",
        options=network_options,
        default=[],
    )

    currency_default_index = 1 if len(currency_options) == 1 else 0
    selected_currency = st.selectbox(
        "Devise d'analyse",
        options=["Toutes"] + currency_options,
        index=currency_default_index,
    )

    years = sorted(
        df["first_seen_at"].dropna().dt.year.unique().tolist()
    )
    year_options = ["Toutes"] + [int(year) for year in years]

    selected_year = st.selectbox(
        "Année de première observation",
        options=year_options,
        help=(
            "Cette date correspond à first_seen_at dans la base, "
            "pas nécessairement à la date de commercialisation."
        ),
    )

    topup_filter = st.selectbox(
        "Recharge",
        [
            "Toutes",
            "Recharge possible",
            "Sans recharge",
            "Non renseignée / format inconnu",
        ],
    )

    plan_filter = st.selectbox(
        "Type de forfait",
        ["Tous", "Volume défini", "Illimité"],
    )

    st.divider()
    st.caption("MyBestSim · Vue analytique")


# Apply cross-filters
if selected_providers:
    df = df[df["provider"].astype(str).isin(selected_providers)]
else:
    df = df.iloc[0:0]

if selected_countries:
    df = df[df["country_name"].astype(str).isin(selected_countries)]

if selected_networks:
    df = df[df["network"].astype(str).isin(selected_networks)]

if selected_currency != "Toutes":
    df = df[df["currency"].astype(str) == selected_currency]

if selected_year != "Toutes":
    df = df[df["first_seen_at"].dt.year == int(selected_year)]

normalized_top_up = normalize_top_up(df["top_up"])

if topup_filter == "Recharge possible":
    df = df[normalized_top_up == "Oui"]
elif topup_filter == "Sans recharge":
    df = df[normalized_top_up == "Non"]
elif topup_filter == "Non renseignée / format inconnu":
    df = df[normalized_top_up.isna()]

if plan_filter == "Illimité":
    df = df[get_unlimited_mask(df)]
elif plan_filter == "Volume défini":
    df = df[df["data_gb"].notna() & ~get_unlimited_mask(df)]


# Price range only makes sense for one currency
if selected_currency != "Toutes" and not df.empty:
    price_values = df["price"].dropna()
    if not price_values.empty:
        price_min = float(price_values.min())
        price_max = float(price_values.max())

        if price_min < price_max:
            selected_price_range = st.sidebar.slider(
                f"Prix ({selected_currency})",
                min_value=price_min,
                max_value=price_max,
                value=(price_min, price_max),
            )
            df = df[
                df["price"].between(
                    selected_price_range[0],
                    selected_price_range[1],
                )
            ]
        else:
            st.sidebar.caption(
                f"Prix observé : {price_min:.2f} {selected_currency}"
            )




def compute_source_hash(row_values: dict) -> str:
    """
    Stable SHA-256 fingerprint of a normalized source row.
    Excludes source_hash itself so recomputing the same row is deterministic.
    """
    canonical_values = {
        str(key): _clean_csv_value(value)
        for key, value in row_values.items()
        if key != "source_hash"
    }
    canonical_json = json.dumps(
        canonical_values,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


# ------------------- CSV management / ingestion -------------------

CSV_REQUIRED_COLUMNS = [
    "sku",
    "provider",
    "product_name",
    "country_code",
    "country_name",
    "data_gb",
    "data_display",
    "validity_days",
    "price",
    "currency",
    "network",
    "top_up",
]


def parse_uploaded_csv(raw_bytes: bytes):
    """Read and validate one provider CSV without changing the database."""
    try:
        csv_df = pd.read_csv(
            io.BytesIO(raw_bytes),
            sep=None,
            engine="python",
            encoding="utf-8-sig",
        )
    except UnicodeDecodeError:
        csv_df = pd.read_csv(
            io.BytesIO(raw_bytes),
            sep=None,
            engine="python",
            encoding="cp1252",
        )

    csv_df.columns = [
        str(column).strip().lower().replace(" ", "_")
        for column in csv_df.columns
    ]

    if csv_df.columns.duplicated().any():
        raise ValueError(
            "Le CSV contient des noms de colonnes dupliqués après normalisation."
        )

    missing_columns = [
        column for column in CSV_REQUIRED_COLUMNS
        if column not in csv_df.columns
    ]
    if missing_columns:
        raise ValueError(
            "Colonnes obligatoires absentes : "
            + ", ".join(missing_columns)
        )

    if csv_df.empty:
        raise ValueError("Le CSV ne contient aucune ligne de données.")

    # Required textual fields.
    for column in ["sku", "provider", "product_name", "currency"]:
        csv_df[column] = csv_df[column].astype("string").str.strip()
        invalid = (
            csv_df[column].isna()
            | csv_df[column].fillna("").eq("")
        )
        if invalid.any():
            raise ValueError(
                f"Le champ « {column} » est vide sur "
                f"{int(invalid.sum())} ligne(s)."
            )

    # A single CSV is expected to represent one provider.
    provider_names = (
        csv_df["provider"].dropna().astype(str).str.strip().unique().tolist()
    )
    if len(provider_names) != 1:
        raise ValueError(
            "Un fichier doit correspondre à un seul fournisseur. "
            f"Fournisseurs détectés : {', '.join(provider_names[:8])}."
        )

    # SKU uniqueness within a single file.
    duplicated_skus = csv_df["sku"].duplicated(keep=False)
    if duplicated_skus.any():
        examples = (
            csv_df.loc[duplicated_skus, "sku"]
            .astype(str)
            .drop_duplicates()
            .head(8)
            .tolist()
        )
        raise ValueError(
            f"{int(duplicated_skus.sum())} ligne(s) présentent des SKU dupliqués. "
            "Exemples : " + ", ".join(examples)
        )

    # Numeric validation. Missing data_gb is allowed for unlimited plans.
    csv_df["price"] = pd.to_numeric(csv_df["price"], errors="coerce")
    if csv_df["price"].isna().any():
        raise ValueError(
            f"Le prix est absent ou non numérique sur "
            f"{int(csv_df['price'].isna().sum())} ligne(s)."
        )
    if (csv_df["price"] < 0).any():
        raise ValueError("Le CSV contient un ou plusieurs prix négatifs.")

    data_gb_original = csv_df["data_gb"].copy()
    csv_df["data_gb"] = pd.to_numeric(csv_df["data_gb"], errors="coerce")
    data_gb_text = data_gb_original.fillna("").astype(str).str.strip()
    unlimited = (
        csv_df["data_display"]
        .fillna("")
        .astype(str)
        .str.contains(r"illimité|illimite|unlimited", case=False, regex=True)
    )
    invalid_data_gb = (
        data_gb_text.ne("")
        & csv_df["data_gb"].isna()
        & ~unlimited
    )
    if invalid_data_gb.any():
        raise ValueError(
            "Certaines valeurs data_gb ne sont pas numériques et ne sont pas "
            "identifiées comme des forfaits illimités."
        )

    validity_original = csv_df["validity_days"].copy()
    csv_df["validity_days"] = pd.to_numeric(
        csv_df["validity_days"], errors="coerce"
    )
    validity_text = validity_original.fillna("").astype(str).str.strip()
    invalid_validity_parse = (
        validity_text.ne("") & csv_df["validity_days"].isna()
    )
    if invalid_validity_parse.any():
        raise ValueError(
            "Certaines valeurs validity_days ne sont pas numériques."
        )
    invalid_validity = (
        csv_df["validity_days"].notna()
        & (csv_df["validity_days"] <= 0)
    )
    if invalid_validity.any():
        raise ValueError("La durée de validité doit être strictement positive.")

    return csv_df, provider_names[0]


def _table_from_connection(connection, table_name):
    metadata = MetaData()
    try:
        return Table(table_name, metadata, autoload_with=connection)
    except Exception as exc:
        raise ValueError(
            f"Impossible de lire la table « {table_name} » dans la base. "
            "Vérifie le schéma PostgreSQL."
        ) from exc


def _prepare_values(table, values, operation_name):
    """Keep only columns present in the reflected table and detect required fields."""
    prepared = {
        key: value
        for key, value in values.items()
        if key in table.c
    }

    missing_required = []
    for column in table.columns:
        if column.name in prepared:
            continue
        if column.primary_key:
            continue
        if column.nullable:
            continue
        if column.default is not None or column.server_default is not None:
            continue
        if getattr(column, "identity", None) is not None:
            continue
        missing_required.append(column.name)

    if missing_required:
        raise ValueError(
            f"Le schéma de la table « {table.name} » exige d'autres champs "
            f"pour {operation_name} : {', '.join(missing_required)}. "
            "Le code d'import doit être adapté à ce schéma."
        )

    return prepared


def _clean_csv_value(value):
    if pd.isna(value):
        return None
    if hasattr(value, "item"):
        try:
            value = value.item()
        except Exception:
            pass
    if isinstance(value, str):
        value = value.strip()
        return value if value != "" else None
    return value


def _top_up_value(value, column_type):
    value = _clean_csv_value(value)
    if value is None:
        return None

    if isinstance(column_type, Boolean):
        normalized = str(value).strip().lower()
        if normalized in {"oui", "yes", "true", "1", "y", "vrai"}:
            return True
        if normalized in {"non", "no", "false", "0", "n", "faux"}:
            return False
        return None

    return str(value).strip().lower()


def import_csv_to_database(database_url: str, filename: str, csv_df: pd.DataFrame):
    """
    Upsert a CSV into the existing providers/datasets/products schema.
    The operation is transactional. Missing old products are deactivated when
    the schema has products.is_active; otherwise they are removed from that dataset.
    """
    engine = get_engine(database_url)
    now = datetime.now(timezone.utc)
    provider_name = str(csv_df["provider"].dropna().iloc[0]).strip()
    sku_values = csv_df["sku"].astype(str).str.strip().tolist()

    inserted_count = 0
    updated_count = 0

    with engine.begin() as connection:
        providers = _table_from_connection(connection, "providers")
        datasets = _table_from_connection(connection, "datasets")
        products = _table_from_connection(connection, "products")

        for table_name, table in [
            ("providers", providers),
            ("datasets", datasets),
            ("products", products),
        ]:
            if "id" not in table.c:
                raise ValueError(
                    f"La table « {table_name} » doit contenir une colonne « id »."
                )

        if "name" not in providers.c:
            raise ValueError("La table providers doit contenir la colonne name.")
        if "filename" not in datasets.c or "provider_id" not in datasets.c:
            raise ValueError(
                "La table datasets doit contenir filename et provider_id."
            )
        if "dataset_id" not in products.c or "sku" not in products.c:
            raise ValueError(
                "La table products doit contenir dataset_id et sku."
            )

        # Find or create the provider.
        provider_row = connection.execute(
            select(providers).where(
                func.lower(providers.c.name) == provider_name.lower()
            )
        ).mappings().first()

        if provider_row:
            provider_id = provider_row["id"]
        else:
            slug = re.sub(
                r"[^a-z0-9]+", "-", provider_name.lower()
            ).strip("-")
            provider_values = _prepare_values(
                providers,
                {
                    "name": provider_name,
                    "slug": slug,
                    "created_at": now,
                    "updated_at": now,
                },
                "création du fournisseur",
            )
            result = connection.execute(
                insert(providers).values(**provider_values).returning(providers.c.id)
            )
            provider_id = result.scalar_one()

        # Find or create dataset by the uploaded filename.
        dataset_row = connection.execute(
            select(datasets).where(datasets.c.filename == filename)
        ).mappings().first()

        if dataset_row:
            dataset_id = dataset_row["id"]
            if dataset_row.get("provider_id") != provider_id:
                raise ValueError(
                    f"Le fichier « {filename} » est déjà associé à un autre "
                    "fournisseur. Renomme le fichier ou vérifie le registre."
                )
        else:
            dataset_values = _prepare_values(
                datasets,
                {
                    "provider_id": provider_id,
                    "filename": filename,
                    "status": "active",
                    "expected": True,
                    "last_row_count": len(csv_df),
                    "last_imported_at": now,
                    "created_at": now,
                    "updated_at": now,
                },
                "création du dataset",
            )
            result = connection.execute(
                insert(datasets).values(**dataset_values).returning(datasets.c.id)
            )
            dataset_id = result.scalar_one()

        if "first_seen_at" in products.c:
            first_seen_value = now
        else:
            first_seen_value = None

        # Upsert each row by dataset_id + SKU.
        for _, row in csv_df.iterrows():
            sku = str(row["sku"]).strip()
            raw_values = {
                column: _clean_csv_value(row[column])
                for column in CSV_REQUIRED_COLUMNS
                if column in csv_df.columns
            }

            # Hash only the source CSV values, not timestamps or database metadata.
            # The same source row therefore receives the same hash on re-import.
            if "source_hash" in products.c:
                raw_values["source_hash"] = compute_source_hash(raw_values)

            raw_values["dataset_id"] = dataset_id
            raw_values["is_active"] = True
            raw_values["last_seen_at"] = now
            raw_values["updated_at"] = now
            if first_seen_value is not None:
                raw_values["first_seen_at"] = first_seen_value

            if "top_up" in products.c:
                raw_values["top_up"] = _top_up_value(
                    row["top_up"], products.c.top_up.type
                )

            # Normalize numeric fields for database insertion.
            for numeric_column in ("price", "data_gb", "validity_days"):
                if numeric_column in raw_values:
                    raw_values[numeric_column] = _clean_csv_value(
                        raw_values[numeric_column]
                    )

            existing_product = connection.execute(
                select(products.c.id).where(
                    products.c.dataset_id == dataset_id,
                    products.c.sku == sku,
                ).limit(1)
            ).scalar_one_or_none()

            if existing_product is not None:
                # Existing rows only need columns that will actually be updated.
                # Preserve first_seen_at, dataset_id and SKU.
                product_values = {
                    key: value
                    for key, value in raw_values.items()
                    if key in products.c
                    and key not in {"first_seen_at", "dataset_id", "sku"}
                }
                connection.execute(
                    update(products)
                    .where(
                        products.c.dataset_id == dataset_id,
                        products.c.sku == sku,
                    )
                    .values(**product_values)
                )
                updated_count += 1
            else:
                product_values = _prepare_values(
                    products, raw_values, f"import du SKU {sku}"
                )
                connection.execute(
                    insert(products).values(**product_values)
                )
                inserted_count += 1

        # Products missing from the newly uploaded snapshot should no longer
        # appear as active catalogue products.
        if "is_active" in products.c:
            inactive_values = {"is_active": False}
            if "updated_at" in products.c:
                inactive_values["updated_at"] = now
            connection.execute(
                update(products)
                .where(
                    products.c.dataset_id == dataset_id,
                    ~products.c.sku.in_(sku_values),
                )
                .values(**inactive_values)
            )
        else:
            connection.execute(
                delete(products).where(
                    products.c.dataset_id == dataset_id,
                    ~products.c.sku.in_(sku_values),
                )
            )

        dataset_updates = {
            "status": "active",
            "expected": True,
            "last_row_count": len(csv_df),
            "last_imported_at": now,
            "updated_at": now,
        }
        dataset_updates = {
            key: value for key, value in dataset_updates.items()
            if key in datasets.c
        }
        connection.execute(
            update(datasets)
            .where(datasets.c.id == dataset_id)
            .values(**dataset_updates)
        )

    # Best-effort logging: an optional history table must not undo a successful import.
    try:
        with engine.begin() as connection:
            if inspect(connection).has_table("import_runs"):
                import_runs = _table_from_connection(connection, "import_runs")
                run_values = _prepare_values(
                    import_runs,
                    {
                        "dataset_id": dataset_id,
                        "started_at": now,
                        "finished_at": now,
                        "status": "succeeded",
                        "total_rows": len(csv_df),
                        "inserted_rows": inserted_count,
                        "updated_rows": updated_count,
                        "unchanged_rows": 0,
                        "rejected_rows": 0,
                        "error_message": None,
                    },
                    "journalisation de l'import",
                )
                connection.execute(insert(import_runs).values(**run_values))
    except Exception:
        # The core data transaction already succeeded. History logging is optional.
        pass

    return {
        "filename": filename,
        "provider": provider_name,
        "rows": len(csv_df),
        "inserted": inserted_count,
        "updated": updated_count,
        "status": "active",
    }


def remove_dataset_from_database(database_url: str, filename: str, permanent: bool):
    """Disable a dataset or permanently remove its products and import history."""
    engine = get_engine(database_url)
    now = datetime.now(timezone.utc)

    with engine.begin() as connection:
        datasets = _table_from_connection(connection, "datasets")
        products = _table_from_connection(connection, "products")

        dataset_row = connection.execute(
            select(datasets).where(datasets.c.filename == filename)
        ).mappings().first()

        if not dataset_row:
            raise ValueError(f"Le dataset « {filename} » n'existe plus.")

        dataset_id = dataset_row["id"]

        if permanent:
            if inspect(connection).has_table("import_runs"):
                import_runs = _table_from_connection(connection, "import_runs")
                if "dataset_id" in import_runs.c:
                    connection.execute(
                        delete(import_runs).where(
                            import_runs.c.dataset_id == dataset_id
                        )
                    )

            if "dataset_id" in products.c:
                connection.execute(
                    delete(products).where(products.c.dataset_id == dataset_id)
                )

            connection.execute(
                delete(datasets).where(datasets.c.id == dataset_id)
            )
            action = "deleted"
        else:
            dataset_values = {"status": "disabled"}
            if "updated_at" in datasets.c:
                dataset_values["updated_at"] = now
            connection.execute(
                update(datasets)
                .where(datasets.c.id == dataset_id)
                .values(**{
                    key: value for key, value in dataset_values.items()
                    if key in datasets.c
                })
            )

            if "is_active" in products.c:
                product_values = {"is_active": False}
                if "updated_at" in products.c:
                    product_values["updated_at"] = now
                connection.execute(
                    update(products)
                    .where(products.c.dataset_id == dataset_id)
                    .values(**product_values)
                )
            action = "disabled"

    return action


def refresh_after_data_change():
    load_products.clear()
    load_datasets.clear()
    load_import_history.clear()



# ---------------------------- Header --------------------------

st.markdown(
    """
    <div class="hero">
        <div>
            <div class="hero-eyebrow">DATA INTELLIGENCE PLATFORM</div>
            <div class="hero-title">MyBestSim Analytics</div>
            <div class="hero-subtitle">
                Explorez le catalogue eSIM, comparez les fournisseurs
                et surveillez la qualité des données.
            </div>
        </div>
        <div class="hero-chip">● Connecté à PostgreSQL / Supabase</div>
    </div>
    """,
    unsafe_allow_html=True,
)

# Search affects all displayed analyses below
search = st.text_input(
    "⌕  Rechercher dans le catalogue",
    placeholder="Nom du produit, SKU, fournisseur, pays ou réseau...",
)

if search.strip():
    searchable_columns = [
        "sku", "product_name", "provider",
        "country_name", "country_code", "network",
        "data_display", "filename",
    ]
    mask = pd.Series(False, index=df.index)

    for column in searchable_columns:
        mask |= (
            df[column]
            .fillna("")
            .astype(str)
            .str.contains(search.strip(), case=False, regex=False)
        )

    df = df[mask]


# ---------------------------- KPIs ----------------------------

currency_label = (
    selected_currency
    if selected_currency != "Toutes"
    else (
        str(df["currency"].dropna().iloc[0])
        if not df.empty and df["currency"].nunique() == 1
        else None
    )
)

c1, c2, c3, c4 = st.columns(4)

c1.metric(
    "Produits filtrés",
    format_count(len(df)),
    help="Nombre de produits correspondant aux filtres actuels.",
)

c2.metric(
    "Fournisseurs",
    format_count(df["provider"].nunique()) if not df.empty else "0",
)

c3.metric(
    "Destinations",
    format_count(df["country_name"].nunique()) if not df.empty else "0",
)

if not df.empty and currency_label:
    c4.metric(
        "Prix médian",
        format_money(df["price"].median(), currency_label),
        help="Calculé uniquement sur les produits de la devise sélectionnée.",
    )
else:
    c4.metric(
        "Prix médian",
        "—",
        help="Sélectionne une devise pour éviter de mélanger des monnaies.",
    )

st.caption(
    f"Affichage de {format_count(len(df))} produit(s) sur "
    f"{format_count(len(products_all))} produit(s) actifs chargés."
)

st.divider()


# ------------------------------ Tabs --------------------------

tab_overview, tab_catalogue, tab_quality, tab_manage = st.tabs(
    ["Vue d'ensemble", "Catalogue détaillé", "Qualité & sources", "Gestion des CSV"]
)


# ============================================================
# TAB 1 — OVERVIEW
# ============================================================

with tab_overview:
    page_heading(
        "Vue d'ensemble",
        "Indicateurs et comparaisons recalculés selon les filtres actifs.",
    )

    if df.empty:
        st.info("Aucun résultat pour cette combinaison de filtres.")
    else:
        if currency_label is None:
            st.info(
                "Les données contiennent plusieurs devises. "
                "Choisis une devise dans la barre latérale pour comparer les prix."
            )

        top_left, top_right = st.columns(2)

        with top_left:
            provider_count = (
                df.groupby("provider")
                .size()
                .reset_index(name="Produits")
                .sort_values("Produits", ascending=False)
            )

            fig = px.bar(
                provider_count,
                x="provider",
                y="Produits",
                title="Nombre de produits par fournisseur",
                labels={"provider": "Fournisseur"},
                color_discrete_sequence=["#079FE3"],
            )
            fig.update_layout(showlegend=False, xaxis_title=None)
            st.plotly_chart(make_chart(fig), use_container_width=True)

        with top_right:
            if currency_label:
                price_by_provider = (
                    df[df["currency"].astype(str) == currency_label]
                    .groupby("provider")["price"]
                    .median()
                    .dropna()
                    .sort_values()
                    .reset_index(name="Prix médian")
                )

                if not price_by_provider.empty:
                    fig = px.bar(
                        price_by_provider,
                        x="Prix médian",
                        y="provider",
                        orientation="h",
                        title=f"Prix médian par fournisseur ({currency_label})",
                        labels={"provider": "Fournisseur"},
                        color_discrete_sequence=["#12B8A6"],
                    )
                    fig.update_layout(showlegend=False)
                    st.plotly_chart(make_chart(fig), use_container_width=True)
                else:
                    st.info("Pas de prix exploitable pour cette sélection.")
            else:
                st.markdown(
                    '<div class="status-note">Sélectionne une devise pour afficher '
                    'une comparaison de prix cohérente.</div>',
                    unsafe_allow_html=True,
                )

        bottom_left, bottom_right = st.columns(2)

        with bottom_left:
            if currency_label:
                price_df = df[
                    (df["currency"].astype(str) == currency_label)
                    & df["price"].notna()
                ]

                if not price_df.empty:
                    fig = px.histogram(
                        price_df,
                        x="price",
                        nbins=30,
                        title=f"Distribution des prix ({currency_label})",
                        labels={"price": f"Prix ({currency_label})"},
                        color_discrete_sequence=["#637CE8"],
                    )
                    fig.update_layout(yaxis_title="Nombre de produits")
                    st.plotly_chart(make_chart(fig), use_container_width=True)
                else:
                    st.info("Aucun prix disponible pour cette sélection.")
            else:
                st.markdown(
                    '<div class="status-note">La distribution des prix nécessite '
                    'une devise unique.</div>',
                    unsafe_allow_html=True,
                )

        with bottom_right:
            country_count = (
                df.groupby("country_name", dropna=False)
                .size()
                .reset_index(name="Produits")
                .sort_values("Produits", ascending=False)
                .head(10)
            )
            country_count["country_name"] = (
                country_count["country_name"]
                .fillna("Non renseigné")
            )

            fig = px.bar(
                country_count.sort_values("Produits"),
                x="Produits",
                y="country_name",
                orientation="h",
                title="Destinations les plus représentées",
                labels={
                    "country_name": "Pays / territoire",
                },
                color_discrete_sequence=["#079FE3"],
            )
            fig.update_layout(showlegend=False)
            st.plotly_chart(make_chart(fig), use_container_width=True)

        st.markdown("#### Résumé statistique")

        summary_rows = [
            {
                "Indicateur": "Volume moyen (Go)",
                "Valeur": (
                    f"{df['data_gb'].mean():.2f} Go"
                    if df["data_gb"].notna().any()
                    else "Non disponible"
                ),
            },
            {
                "Indicateur": "Validité médiane",
                "Valeur": (
                    f"{df['validity_days'].median():.0f} jours"
                    if df["validity_days"].notna().any()
                    else "Non disponible"
                ),
            },
            {
                "Indicateur": "Forfaits illimités identifiés",
                "Valeur": format_count(get_unlimited_mask(df).sum()),
            },
            {
                "Indicateur": "Produits avec prix renseigné",
                "Valeur": format_count(df["price"].notna().sum()),
            },
        ]

        st.dataframe(
            pd.DataFrame(summary_rows),
            use_container_width=True,
            hide_index=True,
        )


# ============================================================
# TAB 2 — CATALOGUE
# ============================================================

with tab_catalogue:
    page_heading(
        "Catalogue détaillé",
        "Recherchez, triez et exportez les produits correspondant à vos critères.",
    )

    if df.empty:
        st.info("Aucun produit ne correspond aux filtres actuels.")
    else:
        sort_options = {
            "Nom du produit": "product_name",
            "Fournisseur": "provider",
            "Pays / territoire": "country_name",
            "Prix": "price",
            "Volume (Go)": "data_gb",
            "Validité (jours)": "validity_days",
            "Réseau": "network",
            "SKU": "sku",
        }

        col_sort, col_order = st.columns([2, 1])

        with col_sort:
            sort_label = st.selectbox(
                "Trier par",
                options=list(sort_options.keys()),
                key="catalog_sort",
            )

        with col_order:
            sort_order = st.selectbox(
                "Ordre",
                options=["Croissant", "Décroissant"],
                key="catalog_order",
            )

        catalog = df.sort_values(
            by=sort_options[sort_label],
            ascending=(sort_order == "Croissant"),
            na_position="last",
        ).copy()

        display_columns = [
            "sku",
            "product_name",
            "provider",
            "country_name",
            "data_display",
            "data_gb",
            "validity_days",
            "price",
            "currency",
            "network",
            "top_up",
            "filename",
        ]

        display_names = {
            "sku": "SKU",
            "product_name": "Produit",
            "provider": "Fournisseur",
            "country_name": "Pays / territoire",
            "data_display": "Données",
            "data_gb": "Volume (Go)",
            "validity_days": "Validité (jours)",
            "price": "Prix",
            "currency": "Devise",
            "network": "Réseau",
            "top_up": "Recharge",
            "filename": "Dataset",
        }

        st.dataframe(
            catalog[display_columns].rename(columns=display_names),
            use_container_width=True,
            hide_index=True,
            height=520,
        )

        csv_bytes = catalog.to_csv(index=False).encode("utf-8-sig")

        st.download_button(
            "Télécharger les résultats en CSV",
            data=csv_bytes,
            file_name="mybestsim_catalogue_filtre.csv",
            mime="text/csv",
            type="primary",
        )


# ============================================================
# TAB 3 — QUALITY & SOURCES
# ============================================================

with tab_quality:
    page_heading(
        "Qualité & sources",
        "Profilage des données filtrées et suivi des fichiers sources.",
    )

    quality_df = df.copy()

    if quality_df.empty:
        st.info(
            "Aucun produit à analyser. Modifie les filtres pour afficher "
            "les indicateurs de qualité."
        )
    else:
        required_columns = [
            "sku",
            "product_name",
            "price",
            "currency",
        ]

        completeness_rows = []

        for column in required_columns:
            non_empty = (
                quality_df[column].notna()
                & quality_df[column].astype(str).str.strip().ne("")
            )
            completeness_rows.append(
                {
                    "Champ": column,
                    "Complétude (%)": round(
                        100 * non_empty.mean(), 2
                    ),
                    "Valeurs manquantes": int((~non_empty).sum()),
                }
            )

        completeness_df = pd.DataFrame(completeness_rows)

        duplicate_count = int(
            quality_df.duplicated(
                subset=["dataset_id", "sku"],
                keep=False,
            ).sum()
        )

        negative_price_count = int(
            (quality_df["price"] < 0).sum()
        )

        missing_price_count = int(
            quality_df["price"].isna().sum()
        )

        invalid_validity_count = int(
            (
                quality_df["validity_days"].notna()
                & (quality_df["validity_days"] <= 0)
            ).sum()
        )

        q1, q2, q3, q4 = st.columns(4)

        q1.metric(
            "SKU / nom / prix / devise",
            f"{completeness_df['Complétude (%)'].mean():.1f}%",
            help="Moyenne simple des taux de présence de ces quatre champs.",
        )

        q2.metric(
            "Lignes avec clés dupliquées",
            format_count(duplicate_count),
        )

        q3.metric(
            "Prix manquants",
            format_count(missing_price_count),
        )

        q4.metric(
            "Prix négatifs",
            format_count(negative_price_count),
        )

        st.caption(
            "Les valeurs manquantes ne sont pas toutes des erreurs. "
            "Par exemple, un volume numérique absent peut correspondre à "
            "un forfait illimité. Les résultats sont des signaux à vérifier, "
            "pas des suppressions automatiques."
        )

        left, right = st.columns(2)

        with left:
            fig = px.bar(
                completeness_df,
                x="Champ",
                y="Complétude (%)",
                range_y=[0, 100],
                title="Complétude des champs essentiels",
                color_discrete_sequence=["#079FE3"],
            )
            fig.update_layout(showlegend=False)
            st.plotly_chart(make_chart(fig, 310), use_container_width=True)

        with right:
            missing_rows = []

            for column in [
                "country_code",
                "country_name",
                "data_gb",
                "data_display",
                "validity_days",
                "network",
                "top_up",
            ]:
                missing_rows.append(
                    {
                        "Champ": column,
                        "Manquants": int(quality_df[column].isna().sum()),
                    }
                )

            missing_df = pd.DataFrame(missing_rows).sort_values("Manquants")

            fig = px.bar(
                missing_df,
                x="Manquants",
                y="Champ",
                orientation="h",
                title="Valeurs manquantes par champ",
                color_discrete_sequence=["#12B8A6"],
            )
            fig.update_layout(showlegend=False)
            st.plotly_chart(make_chart(fig, 310), use_container_width=True)

        st.markdown("#### Contrôles à examiner")

        checks = pd.DataFrame(
            [
                {
                    "Contrôle": "SKU et nom présents",
                    "Résultat": format_count(
                        (
                            quality_df["sku"].isna()
                            | quality_df["product_name"].isna()
                        ).sum()
                    ),
                    "Interprétation": "Lignes avec identifiant ou nom absent",
                },
                {
                    "Contrôle": "Prix absent",
                    "Résultat": format_count(missing_price_count),
                    "Interprétation": "À vérifier selon les règles métier",
                },
                {
                    "Contrôle": "Prix négatif",
                    "Résultat": format_count(negative_price_count),
                    "Interprétation": "Anomalie probable",
                },
                {
                    "Contrôle": "Durée non positive",
                    "Résultat": format_count(invalid_validity_count),
                    "Interprétation": "Durée égale à zéro ou négative",
                },
                {
                    "Contrôle": "Clés (dataset, SKU) dupliquées",
                    "Résultat": format_count(duplicate_count),
                    "Interprétation": "À examiner avant toute déduplication",
                },
            ]
        )

        st.dataframe(
            checks,
            use_container_width=True,
            hide_index=True,
        )

    st.divider()
    st.markdown("#### Inventaire des datasets")

    if datasets_all.empty:
        st.warning(
            "L'inventaire des datasets n'a pas pu être chargé. "
            "Vérifie le schéma de la table datasets."
        )
    else:
        d1, d2, d3, d4 = st.columns(4)

        d1.metric(
            "Fichiers enregistrés",
            format_count(len(datasets_all)),
        )

        d2.metric(
            "Actifs",
            format_count((datasets_all["status"] == "active").sum()),
        )

        d3.metric(
            "En attente",
            format_count((datasets_all["status"] == "pending").sum()),
        )

        d4.metric(
            "En erreur",
            format_count((datasets_all["status"] == "error").sum()),
        )

        st.dataframe(
            datasets_all.rename(
                columns={
                    "filename": "Fichier",
                    "provider": "Fournisseur",
                    "status": "Statut",
                    "expected": "Attendu",
                    "last_row_count": "Lignes dernier import",
                    "last_imported_at": "Dernier import réussi",
                }
            ),
            use_container_width=True,
            hide_index=True,
        )

    with st.expander("Historique récent des imports"):
        try:
            history_df = load_import_history(DATABASE_URL)

            if history_df.empty:
                st.info("Aucun import enregistré.")
            else:
                st.dataframe(
                    history_df.rename(
                        columns={
                            "started_at": "Début",
                            "filename": "Fichier",
                            "status": "Statut",
                            "total_rows": "Lignes totales",
                            "inserted_rows": "Insérées",
                            "updated_rows": "Modifiées",
                            "unchanged_rows": "Inchangées",
                            "rejected_rows": "Rejetées",
                            "error_message": "Message d'erreur",
                        }
                    ),
                    use_container_width=True,
                    hide_index=True,
                )
        except Exception as exc:
            st.warning(
                "L'historique des imports n'est pas disponible. "
                "Vérifie que la table import_runs et ses colonnes existent."
            )
            st.caption(f"Détail technique : {type(exc).__name__}")


# ============================================================
# TAB 4 — CSV MANAGEMENT
# ============================================================

with tab_manage:
    page_heading(
        "Gestion des CSV",
        "Ajoutez ou remplacez un CSV, puis actualisez automatiquement le catalogue analytique.",
    )

    st.markdown(
        """
        <div class="status-note">
            <strong>Fonctionnement :</strong> le fichier est validé puis importé dans
            PostgreSQL/Supabase. Après un import réussi, les caches sont vidés et
            le dashboard recharge les données. Les graphiques, KPI, filtres et tableaux
            reflètent donc le nouveau catalogue au prochain rendu.
            Le fichier source sur votre ordinateur n'est pas modifié.
        </div>
        """,
        unsafe_allow_html=True,
    )

    if not ADMIN_PASSWORD:
        st.warning(
            "Les opérations d'écriture sont désactivées tant que ADMIN_PASSWORD "
            "n'est pas configuré dans le fichier .env. Cela protège l'administration "
            "du dashboard."
        )
        st.code('ADMIN_PASSWORD="UN_MOT_DE_PASSE_LONG_ET_UNIQUE"')
        st.stop()

    if not st.session_state.get("csv_admin_authenticated", False):
        with st.form("csv_admin_login"):
            admin_input = st.text_input(
                "Mot de passe administrateur",
                type="password",
            )
            login_submit = st.form_submit_button(
                "Déverrouiller la gestion des CSV",
                type="primary",
            )

        if login_submit:
            if hmac.compare_digest(admin_input, ADMIN_PASSWORD):
                st.session_state["csv_admin_authenticated"] = True
                st.rerun()
            else:
                st.error("Mot de passe incorrect.")

        st.stop()

    admin_col1, admin_col2 = st.columns([4, 1])
    with admin_col1:
        st.success("Administration déverrouillée pour cette session.")
    with admin_col2:
        if st.button("Verrouiller"):
            st.session_state["csv_admin_authenticated"] = False
            st.rerun()

    st.divider()

    upload_tab, remove_tab = st.tabs(
        ["Importer / remplacer un CSV", "Retirer / supprimer un dataset"]
    )

    with upload_tab:
        st.markdown("#### 1. Sélectionner un CSV")
        uploaded_csv = st.file_uploader(
            "Déposer un fichier CSV (un fournisseur par fichier)",
            type=["csv"],
            key="managed_csv_upload",
            help=(
                "Le fichier doit comporter les colonnes attendues par le pipeline "
                "MyBestSim : sku, provider, product_name, country_code, country_name, "
                "data_gb, data_display, validity_days, price, currency, network, top_up."
            ),
        )

        if uploaded_csv is not None:
            upload_filename = Path(uploaded_csv.name).name
            upload_bytes = uploaded_csv.getvalue()

            try:
                preview_df, detected_provider = parse_uploaded_csv(upload_bytes)
                registered_names = (
                    datasets_all["filename"].dropna().astype(str).tolist()
                    if not datasets_all.empty else []
                )
                is_replacement = upload_filename in registered_names

                st.markdown("#### 2. Vérifier le fichier")
                info1, info2, info3 = st.columns(3)
                info1.metric("Lignes détectées", format_count(len(preview_df)))
                info2.metric("Fournisseur détecté", detected_provider)
                info3.metric(
                    "Mode",
                    "Remplacement / mise à jour" if is_replacement else "Nouveau dataset",
                )

                if is_replacement:
                    st.warning(
                        f"Le fichier « {upload_filename} » existe déjà. "
                        "Les produits de ce dataset seront mis à jour ; les SKU absents "
                        "du nouveau CSV seront désactivés."
                    )
                    replace_confirm = st.checkbox(
                        "Je confirme la mise à jour de ce dataset existant.",
                        key=f"replace_confirm_{upload_filename}",
                    )
                else:
                    st.info(
                        "Ce nom de fichier n'est pas encore enregistré. "
                        "Le fournisseur sera associé ou créé si nécessaire."
                    )
                    replace_confirm = True

                st.dataframe(
                    preview_df.head(12),
                    use_container_width=True,
                    hide_index=True,
                )

                if st.button(
                    "Importer et actualiser le dashboard",
                    type="primary",
                    disabled=not replace_confirm,
                    key="run_csv_import",
                ):
                    try:
                        with st.spinner(
                            "Validation finale et import transactionnel dans Supabase..."
                        ):
                            result = import_csv_to_database(
                                DATABASE_URL,
                                upload_filename,
                                preview_df,
                            )

                        refresh_after_data_change()
                        st.success(
                            f"Import réussi : {result['filename']} — "
                            f"{format_count(result['rows'])} lignes. "
                            f"{format_count(result['inserted'])} ajoutées, "
                            f"{format_count(result['updated'])} mises à jour."
                        )
                        st.info(
                            "Le dashboard va maintenant recharger les données "
                            "et recalculer les indicateurs."
                        )
                        st.rerun()

                    except Exception as exc:
                        st.error(
                            "L'import a échoué. La transaction principale a été "
                            "annulée si une erreur est survenue pendant l'écriture."
                        )
                        st.code(f"{type(exc).__name__}: {exc}")

            except Exception as exc:
                st.error("Le CSV n'a pas passé la validation.")
                st.code(f"{type(exc).__name__}: {exc}")

        st.caption(
            "Le schéma est vérifié avant l'écriture. Les SKU dupliqués, les prix "
            "négatifs, les colonnes obligatoires absentes et les fichiers contenant "
            "plusieurs fournisseurs sont refusés."
        )

    with remove_tab:
        st.markdown("#### Retirer du dashboard (réversible)")

        if datasets_all.empty:
            st.info("Aucun dataset enregistré.")
        else:
            all_filenames = (
                datasets_all["filename"].dropna().astype(str).sort_values().tolist()
            )

            active_or_pending = datasets_all[
                datasets_all["status"].astype(str).isin(
                    ["active", "pending", "error"]
                )
            ]["filename"].dropna().astype(str).sort_values().tolist()

            if active_or_pending:
                soft_filename = st.selectbox(
                    "Dataset à retirer",
                    active_or_pending,
                    key="soft_remove_filename",
                )
                soft_confirm = st.checkbox(
                    f"Confirmer le retrait de « {soft_filename} » du dashboard.",
                    key="soft_remove_confirm",
                )

                if st.button(
                    "Retirer du dashboard",
                    disabled=not soft_confirm,
                    key="soft_remove_button",
                ):
                    try:
                        remove_dataset_from_database(
                            DATABASE_URL,
                            soft_filename,
                            permanent=False,
                        )
                        refresh_after_data_change()
                        st.success(
                            "Dataset désactivé. Ses données sont conservées en base "
                            "et le retrait est réversible."
                        )
                        st.rerun()
                    except Exception as exc:
                        st.error("Le dataset n'a pas pu être désactivé.")
                        st.code(f"{type(exc).__name__}: {exc}")
            else:
                st.info("Aucun dataset actif ou en attente à retirer.")

        st.divider()
        st.markdown("#### Supprimer définitivement de Supabase")
        st.warning(
            "Cette action supprime le dataset, ses produits et son historique d'import "
            "associé. Elle ne supprime pas le CSV original de votre ordinateur. "
            "La suppression est irréversible."
        )

        if not datasets_all.empty:
            permanent_filename = st.selectbox(
                "Dataset à supprimer définitivement",
                datasets_all["filename"].dropna().astype(str).sort_values().tolist(),
                key="permanent_delete_filename",
            )
            typed_filename = st.text_input(
                "Pour confirmer, retape exactement le nom du fichier",
                key="typed_permanent_filename",
            )
            permanent_confirm = st.checkbox(
                "Je comprends que les données et l'historique associés seront supprimés.",
                key="permanent_delete_confirm",
            )

            can_delete = (
                typed_filename.strip() == permanent_filename
                and permanent_confirm
            )

            if st.button(
                "Supprimer définitivement",
                type="primary",
                disabled=not can_delete,
                key="permanent_delete_button",
            ):
                try:
                    remove_dataset_from_database(
                        DATABASE_URL,
                        permanent_filename,
                        permanent=True,
                    )
                    refresh_after_data_change()
                    st.success(
                        f"Le dataset « {permanent_filename} » et ses données associées "
                        "ont été supprimés de Supabase."
                    )
                    st.rerun()
                except Exception as exc:
                    st.error(
                        "La suppression définitive a échoué. La base a peut-être "
                        "d'autres relations qui empêchent la suppression."
                    )
                    st.code(f"{type(exc).__name__}: {exc}")

