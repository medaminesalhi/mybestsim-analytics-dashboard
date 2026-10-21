
from pathlib import Path
import hashlib
import zipfile
import pandas as pd

# 1. Configuration du projet
ZIP_PATH = Path("donnees-test-mybestsim.zip")
REPORTS_DIR = Path("reports")

# 2. Deux fichiers gardes pour la demonstration
HOLDOUT_FILES = {"gigsky.csv", "esimx.csv"}

# 3. Schema attendu pour les CSV
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


def read_csv_from_zip(archive, filename):
    """Lit un CSV depuis le ZIP."""
    with archive.open(filename) as file_obj:
        df = pd.read_csv(
            file_obj,
            sep=None,
            engine="python",
            encoding="utf-8-sig",
        )

    # Nettoyer les espaces dans les noms de colonnes
    df.columns = df.columns.astype(str).str.strip()
    return df


def main():

    # 4. Verifier que le ZIP existe
    if not ZIP_PATH.exists():
        raise FileNotFoundError(
            "Place le ZIP a cote de audit_data.py "
            "et nomme-le donnees-test-mybestsim.zip."
        )

    REPORTS_DIR.mkdir(exist_ok=True)

    inventory_rows = []
    quality_rows = []
    all_frames = []
    initial_frames = []

    # 5. Ouvrir l'archive sans extraire les CSV
    with zipfile.ZipFile(ZIP_PATH) as archive:

        csv_files = sorted(
            name for name in archive.namelist()
            if name.lower().endswith(".csv")
            and not name.startswith("__MACOSX/")
        )

        if len(csv_files) != 18:
            print(
                f"Attention : 18 CSV attendus, "
                f"{len(csv_files)} trouves."
            )

        # 6. Traiter chaque dataset
        for filename in csv_files:

            file_name = Path(filename).name
            raw_bytes = archive.read(filename)
            df = read_csv_from_zip(archive, filename)

            # Verifier le schema
            missing_columns = sorted(
                EXPECTED_COLUMNS - set(df.columns)
            )
            extra_columns = sorted(
                set(df.columns) - EXPECTED_COLUMNS
            )
            schema_ok = (
                not missing_columns and not extra_columns
            )

            # Identifier le fournisseur
            if "provider" in df.columns:
                providers = df["provider"].dropna().astype(str)
            else:
                providers = pd.Series(dtype=str)

            if not providers.empty:
                provider = providers.mode().iloc[0]
            else:
                provider = Path(file_name).stem

            # Compter les forfaits illimites
            if "data_display" in df.columns:
                unlimited_count = df[
                    "data_display"
                ].astype(str).str.contains(
                    "illimité", case=False, na=False
                ).sum()
            else:
                unlimited_count = 0

            # 7. Construire l'inventaire des datasets
            inventory_rows.append({
                "fichier": file_name,
                "fournisseur": provider,
                "statut_initial": (
                    "A AJOUTER - DEMO"
                    if file_name in HOLDOUT_FILES
                    else "CHARGE AU DEPART"
                ),
                "nombre_lignes": len(df),
                "nombre_colonnes": len(df.columns),
                "schema_conforme": schema_ok,
                "colonnes_absentes": ", ".join(
                    missing_columns
                ),
                "colonnes_supplementaires": ", ".join(
                    extra_columns
                ),
                "data_gb_manquant": (
                    int(df["data_gb"].isna().sum())
                    if "data_gb" in df.columns else None
                ),
                "forfaits_illimites": int(unlimited_count),
                "codes_pays_manquants": (
                    int(df["country_code"].isna().sum())
                    if "country_code" in df.columns else None
                ),
                "prix_manquants": (
                    int(df["price"].isna().sum())
                    if "price" in df.columns else None
                ),
                "sku_dupliques": (
                    int(df["sku"].duplicated().sum())
                    if "sku" in df.columns else None
                ),
                "sha256": hashlib.sha256(
                    raw_bytes
                ).hexdigest(),
            })

            # 8. Mesurer la qualite de chaque colonne
            for column in df.columns:
                missing_count = int(df[column].isna().sum())

                quality_rows.append({
                    "fichier": file_name,
                    "colonne": column,
                    "valeurs_manquantes": missing_count,
                    "pourcentage_manquant": round(
                        100 * missing_count / len(df), 2
                    ) if len(df) else 0,
                })

            # Garder le nom du fichier source
            df = df.copy()
            df["source_file"] = file_name
            all_frames.append(df)

            # Ne charger que 16 datasets au depart
            if file_name not in HOLDOUT_FILES:
                initial_frames.append(df)

    # 9. Fusionner les donnees
    inventory = pd.DataFrame(inventory_rows)
    quality = pd.DataFrame(quality_rows)

    all_data = pd.concat(
        all_frames, ignore_index=True, sort=False
    )
    initial_data = pd.concat(
        initial_frames, ignore_index=True, sort=False
    )

    # 10. Exporter les resultats de l'audit
    inventory.to_csv(
        REPORTS_DIR / "dataset_inventory.csv",
        index=False, encoding="utf-8-sig"
    )
    quality.to_csv(
        REPORTS_DIR / "column_quality.csv",
        index=False, encoding="utf-8-sig"
    )
    initial_data.to_csv(
        REPORTS_DIR / "catalogue_initial_16.csv",
        index=False, encoding="utf-8-sig"
    )

    # 11. Calculer quelques indicateurs globaux
    prices = pd.to_numeric(
        all_data["price"], errors="coerce"
    )
    data_gb = pd.to_numeric(
        all_data["data_gb"], errors="coerce"
    )

    print("\n=== AUDIT MYBESTSIM ===")
    print(f"Fichiers : {len(inventory)}")
    print(f"Produits initiaux : {len(initial_data)}")
    print(f"Produits dans les 18 CSV : {len(all_data)}")
    print(f"SKU dupliques : {all_data['sku'].duplicated().sum()}")
    print(f"Prix manquants : {all_data['price'].isna().sum()}")
    print(
        "Codes pays manquants :",
        all_data["country_code"].isna().sum()
    )
    print(
        "Volumes numeriques manquants :",
        all_data["data_gb"].isna().sum()
    )
    print(f"Prix minimum : {prices.min():.2f} EUR")
    print(f"Prix maximum : {prices.max():.2f} EUR")
    print(f"Prix moyen : {prices.mean():.2f} EUR")
    print(f"Produits a plus de 100 EUR : {(prices > 100).sum()}")
    print(
        "Moyenne des Go (offres non illimitees) :",
        round(data_gb.mean(), 2)
    )

    print("\nRapports crees dans reports/ :")
    print("- dataset_inventory.csv")
    print("- column_quality.csv")
    print("- catalogue_initial_16.csv")


if __name__ == "__main__":
    main()
