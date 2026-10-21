
import os
import io
import json
import hashlib
import zipfile

from pathlib import Path
from decimal import Decimal, InvalidOperation

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text, bindparam


# =====================================================
# 1. CONFIGURATION
# =====================================================

load_dotenv()

ZIP_PATH = Path(
    os.getenv("ZIP_PATH", "donnees-test-mybestsim.zip")
)

DATABASE_URL = os.getenv("DATABASE_URL")

# Ces deux fichiers seront importes dans une etape ulterieure.
HOLDOUT_FILES = {"gigsky.csv", "esimx.csv"}

EXPECTED_COLUMNS = {
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
}

# False par defaut : ne pas considerer une absence comme
# une suppression sans avoir confirme que le CSV est complet.
FULL_SNAPSHOT = False


# =====================================================
# 2. CONNEXION POSTGRESQL
# =====================================================

def create_db_engine():
    if not DATABASE_URL:
        raise RuntimeError(
            "DATABASE_URL absent du fichier .env"
        )

    url = DATABASE_URL

    if url.startswith("postgres://"):
        url = url.replace(
            "postgres://",
            "postgresql+psycopg://",
            1,
        )
    elif url.startswith("postgresql://"):
        url = url.replace(
            "postgresql://",
            "postgresql+psycopg://",
            1,
        )

    return create_engine(
        url,
        pool_pre_ping=True,
    )


# =====================================================
# 3. FONCTIONS DE NORMALISATION
# =====================================================

def clean_text(value):
    if value is None or pd.isna(value):
        return None

    value = str(value).strip()
    return value if value else None


def parse_decimal(value, field, required=False):
    if (
        value is None
        or pd.isna(value)
        or str(value).strip() == ""
    ):
        if required:
            raise ValueError(f"{field} est obligatoire")
        return None

    try:
        number = Decimal(
            str(value).strip().replace(",", ".")
        )
    except InvalidOperation:
        raise ValueError(
            f"{field} n'est pas un nombre valide"
        )

    if not number.is_finite():
        raise ValueError(f"{field} n'est pas fini")

    return number


def parse_integer(value, field):
    number = parse_decimal(value, field)

    if number is None:
        return None

    if number != number.to_integral_value():
        raise ValueError(
            f"{field} doit etre un entier"
        )

    return int(number)


def parse_boolean(value):
    value = clean_text(value)

    if value is None:
        return None

    mapping = {
        "oui": True,
        "yes": True,
        "true": True,
        "1": True,
        "non": False,
        "no": False,
        "false": False,
        "0": False,
    }

    result = mapping.get(value.casefold())

    if result is None:
        raise ValueError(
            f"Valeur top_up non reconnue : {value}"
        )

    return result


def json_safe(value):
    if value is None or pd.isna(value):
        return None

    if hasattr(value, "item"):
        value = value.item()

    if isinstance(value, (str, int, float, bool)):
        return value

    return str(value)


def insert_rejections(conn, run_id, rejected):
    if not rejected:
        return

    rows = []

    for item in rejected:
        rows.append({
            "run_id": run_id,
            "row_number": item["row_number"],
            "row_data": json.dumps(
                item["row_data"],
                ensure_ascii=False,
                allow_nan=False,
            ),
            "error": item["error"],
        })

    conn.execute(
        text("""
            INSERT INTO rejected_rows (
                import_run_id,
                source_row_number,
                row_data,
                error_message
            )
            VALUES (
                :run_id,
                :row_number,
                CAST(:row_data AS JSONB),
                :error
            )
        """),
        rows,
    )


# =====================================================
# 4. REGISTRE DES DATASETS
# =====================================================

def get_dataset(conn, filename, lock=False):
    query = """
        SELECT
            d.id,
            d.filename,
            d.status,
            d.last_checksum,
            d.last_row_count,
            p.name AS provider_name
        FROM datasets d
        JOIN providers p
            ON p.id = d.provider_id
        WHERE d.filename = :filename
    """

    if lock:
        query += " FOR UPDATE OF d"

    return conn.execute(
        text(query),
        {"filename": filename},
    ).mappings().first()


def record_failed_run(
    engine,
    filename,
    checksum,
    error,
    total_rows=0,
    rejected=None,
):
    rejected = rejected or []

    with engine.begin() as conn:
        dataset = get_dataset(
            conn, filename, lock=True
        )

        if dataset is None:
            print(
                f"{filename} : dataset absent du registre."
            )
            return

        run_id = conn.execute(
            text("""
                INSERT INTO import_runs (
                    dataset_id,
                    checksum,
                    status,
                    total_rows,
                    rejected_rows,
                    finished_at,
                    error_message
                )
                VALUES (
                    :dataset_id,
                    :checksum,
                    'failed',
                    :total_rows,
                    :rejected_rows,
                    NOW(),
                    :error
                )
                RETURNING id
            """),
            {
                "dataset_id": dataset["id"],
                "checksum": checksum,
                "total_rows": total_rows,
                "rejected_rows": len(rejected),
                "error": str(error)[:4000],
            },
        ).scalar_one()

        insert_rejections(conn, run_id, rejected)

        # Conserver un ancien catalogue actif si un nouvel
        # import echoue.
        if dataset["status"] in {
            "pending", "uploaded", "error"
        }:
            conn.execute(
                text("""
                    UPDATE datasets
                    SET status = 'error',
                        updated_at = NOW()
                    WHERE id = :dataset_id
                """),
                {"dataset_id": dataset["id"]},
            )


# =====================================================
# 5. VALIDATION ET NORMALISATION DES LIGNES
# =====================================================

def normalize_rows(df, expected_provider):
    normalized = []
    rejected = []
    seen_skus = set()

    for index, row in df.iterrows():
        raw_row = {
            key: json_safe(value)
            for key, value in row.to_dict().items()
        }

        try:
            sku = clean_text(row["sku"])
            provider = clean_text(row["provider"])
            product_name = clean_text(
                row["product_name"]
            )

            if not sku:
                raise ValueError("SKU manquant")

            if sku in seen_skus:
                raise ValueError(
                    f"SKU duplique dans le fichier : {sku}"
                )

            if provider != expected_provider:
                raise ValueError(
                    f"Fournisseur inattendu : {provider}"
                )

            if not product_name:
                raise ValueError(
                    "Nom de produit manquant"
                )

            price = parse_decimal(
                row["price"], "price", required=True
            )

            if price < 0:
                raise ValueError("Prix negatif")

            currency = clean_text(row["currency"])

            if not currency or len(currency) != 3:
                raise ValueError(
                    "Code devise invalide"
                )

            currency = currency.upper()

            data_gb = parse_decimal(
                row["data_gb"], "data_gb"
            )

            if data_gb is not None and data_gb < 0:
                raise ValueError(
                    "Volume de donnees negatif"
                )

            validity_days = parse_integer(
                row["validity_days"],
                "validity_days",
            )

            if (
                validity_days is not None
                and validity_days <= 0
            ):
                raise ValueError(
                    "Duree de validite invalide"
                )

            record = {
                "sku": sku,
                "product_name": product_name,
                "country_code": clean_text(
                    row["country_code"]
                ),
                "country_name": clean_text(
                    row["country_name"]
                ),
                "data_gb": data_gb,
                "data_display": clean_text(
                    row["data_display"]
                ),
                "validity_days": validity_days,
                "price": price,
                "currency": currency,
                "network": clean_text(row["network"]),
                "top_up": parse_boolean(row["top_up"]),
            }

            # Une empreinte par produit pour detecter
            # les changements entre deux imports.
            hash_payload = {
                key: (
                    format(value.normalize(), "f")
                    if isinstance(value, Decimal)
                    else value
                )
                for key, value in record.items()
            }

            canonical = json.dumps(
                hash_payload,
                sort_keys=True,
                ensure_ascii=False,
            )

            record["source_hash"] = hashlib.sha256(
                canonical.encode("utf-8")
            ).hexdigest()

            normalized.append(record)
            seen_skus.add(sku)

        except Exception as exc:
            rejected.append({
                "row_number": int(index) + 2,
                "row_data": raw_row,
                "error": str(exc),
            })

    return normalized, rejected


# =====================================================
# 6. IMPORT D'UN DATASET
# =====================================================

def process_dataset(
    engine, filename, raw_bytes, checksum
):
    # Eviter de retraiter un fichier strictement identique.
    with engine.begin() as conn:
        dataset = get_dataset(
            conn, filename, lock=True
        )

        if dataset is None:
            raise ValueError(
                f"{filename} n'est pas enregistre dans datasets"
            )

        if dataset["status"] == "disabled":
            raise ValueError(
                f"{filename} est desactive"
            )

        if (
            dataset["status"] == "active"
            and dataset["last_checksum"] == checksum
        ):
            conn.execute(
                text("""
                    INSERT INTO import_runs (
                        dataset_id,
                        checksum,
                        status,
                        total_rows,
                        finished_at
                    )
                    VALUES (
                        :dataset_id,
                        :checksum,
                        'skipped',
                        :total_rows,
                        NOW()
                    )
                """),
                {
                    "dataset_id": dataset["id"],
                    "checksum": checksum,
                    "total_rows": (
                        dataset["last_row_count"] or 0
                    ),
                },
            )

            return {
                "status": "skipped",
                "filename": filename,
            }

        expected_provider = dataset["provider_name"]

    # Lire le CSV depuis les octets du ZIP.
    df = pd.read_csv(
        io.BytesIO(raw_bytes),
        sep=None,
        engine="python",
        encoding="utf-8-sig",
    )

    df.columns = df.columns.astype(str).str.strip()

    missing = EXPECTED_COLUMNS - set(df.columns)
    extra = set(df.columns) - EXPECTED_COLUMNS

    if missing or extra:
        raise ValueError(
            f"Schema incorrect. Colonnes absentes : "
            f"{sorted(missing)} ; supplementaires : "
            f"{sorted(extra)}"
        )

    normalized, rejected = normalize_rows(
        df, expected_provider
    )

    # Un fichier entierement invalide ne doit pas
    # remplacer un catalogue valide.
    if not normalized:
        error = "Aucune ligne valide dans le fichier."
        record_failed_run(
            engine,
            filename,
            checksum,
            error,
            total_rows=len(df),
            rejected=rejected,
        )

        return {
            "status": "failed",
            "filename": filename,
            "error": error,
        }

    # Toutes les modifications du catalogue sont dans
    # une transaction par dataset.
    with engine.begin() as conn:
        dataset = get_dataset(
            conn, filename, lock=True
        )

        if dataset is None:
            raise ValueError(
                "Dataset introuvable dans le registre"
            )

        if dataset["status"] == "disabled":
            raise ValueError(
                "Dataset desactive pendant le traitement"
            )

        # Verification supplementaire pour eviter un
        # double traitement concurrent.
        if (
            dataset["status"] == "active"
            and dataset["last_checksum"] == checksum
        ):
            conn.execute(
                text("""
                    INSERT INTO import_runs (
                        dataset_id, checksum, status,
                        total_rows, finished_at
                    )
                    VALUES (
                        :dataset_id, :checksum, 'skipped',
                        :total_rows, NOW()
                    )
                """),
                {
                    "dataset_id": dataset["id"],
                    "checksum": checksum,
                    "total_rows": len(df),
                },
            )

            return {
                "status": "skipped",
                "filename": filename,
            }

        dataset_id = dataset["id"]

        run_id = conn.execute(
            text("""
                INSERT INTO import_runs (
                    dataset_id,
                    checksum,
                    status,
                    total_rows
                )
                VALUES (
                    :dataset_id,
                    :checksum,
                    'running',
                    :total_rows
                )
                RETURNING id
            """),
            {
                "dataset_id": dataset_id,
                "checksum": checksum,
                "total_rows": len(df),
            },
        ).scalar_one()

        # Charger les SKU deja connus pour ce dataset.
        existing_rows = conn.execute(
            text("""
                SELECT id, sku, source_hash, is_active
                FROM products
                WHERE dataset_id = :dataset_id
            """),
            {"dataset_id": dataset_id},
        ).mappings().all()

        existing = {
            row["sku"]: dict(row)
            for row in existing_rows
        }

        new_records = []
        changed_records = []
        unchanged_records = []

        for record in normalized:
            old = existing.get(record["sku"])

            if old is None:
                new_records.append({
                    **record,
                    "dataset_id": dataset_id,
                })

            elif old["source_hash"] != record["source_hash"]:
                changed_records.append({
                    **record,
                    "id": old["id"],
                })

            else:
                unchanged_records.append({
                    "id": old["id"],
                })

        # A. Inserer les nouveaux produits.
        if new_records:
            conn.execute(
                text("""
                    INSERT INTO products (
                        dataset_id, sku, product_name,
                        country_code, country_name,
                        data_gb, data_display,
                        validity_days, price, currency,
                        network, top_up, source_hash,
                        is_active
                    )
                    VALUES (
                        :dataset_id, :sku, :product_name,
                        :country_code, :country_name,
                        :data_gb, :data_display,
                        :validity_days, :price, :currency,
                        :network, :top_up, :source_hash,
                        TRUE
                    )
                """),
                new_records,
            )

        # B. Mettre a jour les produits modifies.
        if changed_records:
            conn.execute(
                text("""
                    UPDATE products
                    SET product_name = :product_name,
                        country_code = :country_code,
                        country_name = :country_name,
                        data_gb = :data_gb,
                        data_display = :data_display,
                        validity_days = :validity_days,
                        price = :price,
                        currency = :currency,
                        network = :network,
                        top_up = :top_up,
                        source_hash = :source_hash,
                        is_active = TRUE,
                        last_seen_at = NOW(),
                        updated_at = NOW()
                    WHERE id = :id
                """),
                changed_records,
            )

        # C. Actualiser la date d'observation des produits
        # inchanges sans reecrire leurs caracteristiques.
        if unchanged_records:
            conn.execute(
                text("""
                    UPDATE products
                    SET is_active = TRUE,
                        last_seen_at = NOW()
                    WHERE id = :id
                """),
                unchanged_records,
            )

        # D. Desactiver les produits absents uniquement
        # si le CSV est un snapshot complet confirme et
        # qu'aucune ligne n'a ete rejetee.
        incoming_skus = {
            record["sku"] for record in normalized
        }

        removed = [
            old
            for sku, old in existing.items()
            if sku not in incoming_skus and old["is_active"]
        ]

        if FULL_SNAPSHOT and not rejected and removed:
            conn.execute(
                text("""
                    UPDATE products
                    SET is_active = FALSE,
                        updated_at = NOW()
                    WHERE id = :id
                """),
                [{"id": row["id"]} for row in removed],
            )
        else:
            removed = []

        # E. Retrouver les identifiants des produits.
        sku_query = text("""
            SELECT id, sku
            FROM products
            WHERE dataset_id = :dataset_id
              AND sku IN :skus
        """).bindparams(
            bindparam("skus", expanding=True)
        )

        product_rows = conn.execute(
            sku_query,
            {
                "dataset_id": dataset_id,
                "skus": list(incoming_skus),
            },
        ).mappings().all()

        product_ids = {
            row["sku"]: row["id"]
            for row in product_rows
        }

        # F. Conserver le prix observe pour chaque produit
        # et chaque execution reussie.
        history_rows = [
            {
                "product_id": product_ids[record["sku"]],
                "import_run_id": run_id,
                "price": record["price"],
                "currency": record["currency"],
            }
            for record in normalized
        ]

        conn.execute(
            text("""
                INSERT INTO product_price_history (
                    product_id,
                    import_run_id,
                    price,
                    currency
                )
                VALUES (
                    :product_id,
                    :import_run_id,
                    :price,
                    :currency
                )
                ON CONFLICT (product_id, import_run_id)
                DO NOTHING
            """),
            history_rows,
        )

        # G. Enregistrer les rejets avec leur motif.
        insert_rejections(conn, run_id, rejected)

        # H. Terminer l'execution et mettre a jour le registre.
        conn.execute(
            text("""
                UPDATE import_runs
                SET status = 'succeeded',
                    inserted_rows = :inserted,
                    updated_rows = :updated,
                    unchanged_rows = :unchanged,
                    rejected_rows = :rejected,
                    deactivated_rows = :deactivated,
                    finished_at = NOW()
                WHERE id = :run_id
            """),
            {
                "run_id": run_id,
                "inserted": len(new_records),
                "updated": len(changed_records),
                "unchanged": len(unchanged_records),
                "rejected": len(rejected),
                "deactivated": len(removed),
            },
        )

        conn.execute(
            text("""
                UPDATE datasets
                SET status = 'active',
                    last_checksum = :checksum,
                    last_imported_at = NOW(),
                    last_row_count = :row_count,
                    updated_at = NOW()
                WHERE id = :dataset_id
            """),
            {
                "dataset_id": dataset_id,
                "checksum": checksum,
                "row_count": len(df),
            },
        )

    return {
        "status": "succeeded",
        "filename": filename,
        "inserted": len(new_records),
        "updated": len(changed_records),
        "unchanged": len(unchanged_records),
        "rejected": len(rejected),
        "deactivated": len(removed),
    }


# =====================================================
# 7. POINT D'ENTREE DU PIPELINE
# =====================================================

def main():
    if not ZIP_PATH.exists():
        raise FileNotFoundError(
            f"Archive introuvable : {ZIP_PATH}"
        )

    engine = create_db_engine()
    failures = []

    try:
        with zipfile.ZipFile(ZIP_PATH) as archive:
            csv_members = [
                name for name in archive.namelist()
                if name.lower().endswith(".csv")
                and not name.startswith("__MACOSX/")
            ]

            print(f"CSV trouves : {len(csv_members)}")

            for member in sorted(csv_members):
                filename = Path(member).name

                if filename in HOLDOUT_FILES:
                    print(
                        f"[RESERVE] {filename} "
                        "- non importe pour le moment"
                    )
                    continue

                raw_bytes = archive.read(member)
                checksum = hashlib.sha256(
                    raw_bytes
                ).hexdigest()

                try:
                    result = process_dataset(
                        engine,
                        filename,
                        raw_bytes,
                        checksum,
                    )

                    print(f"[{result['status'].upper()}] {filename}")

                    if result["status"] == "succeeded":
                        print(
                            f"  Inseres : {result['inserted']} | "
                            f"Modifies : {result['updated']} | "
                            f"Inchanges : {result['unchanged']} | "
                            f"Rejetes : {result['rejected']}"
                        )

                    elif result["status"] == "failed":
                        failures.append(filename)
                        print(f"  Erreur : {result['error']}")

                except Exception as exc:
                    print(f"[ERREUR] {filename} : {exc}")

                    try:
                        record_failed_run(
                            engine,
                            filename,
                            checksum,
                            str(exc),
                        )
                    except Exception as log_error:
                        print(
                            "Impossible d'enregistrer l'erreur :",
                            log_error,
                        )

                    failures.append(filename)

    finally:
        engine.dispose()

    print("\n=== BILAN DU PIPELINE ===")
    print(f"Fichiers en erreur : {len(failures)}")

    if failures:
        print("A verifier :", ", ".join(failures))
        raise SystemExit(1)

    print("Traitement termine sans erreur.")


if __name__ == "__main__":
    main()
