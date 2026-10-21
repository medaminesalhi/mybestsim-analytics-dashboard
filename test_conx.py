
import os
import sys

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError


def main():
    # 1. Charger les variables du fichier .env
    load_dotenv()

    database_url = os.getenv("DATABASE_URL")

    if not database_url:
        print("ERREUR : DATABASE_URL est absent du fichier .env")
        sys.exit(1)

    # 2. Analyser la chaine de connexion
    try:
        url = make_url(database_url)

        # Utiliser le pilote psycopg 3
        if url.drivername in ("postgresql", "postgres"):
            url = url.set(drivername="postgresql+psycopg")

    except Exception as error:
        print("ERREUR : chaine de connexion invalide.")
        print(type(error).__name__, str(error))
        sys.exit(1)

    # 3. Afficher les informations non sensibles
    print("=" * 45)
    print("TEST DE CONNEXION SUPABASE")
    print("=" * 45)

    print("Hote :", url.host)
    print("Port :", url.port or 5432)
    print("Utilisateur :", url.username)
    print("Mot de passe : masque")
    print("\nConnexion en cours...")

    engine = None

    try:
        # 4. Creer le moteur SQLAlchemy
        engine = create_engine(
            url,
            connect_args={
                "sslmode": "require",
                "connect_timeout": 10,
            },
            pool_pre_ping=True,
        )

        # 5. Tester la connexion et executer une requete
        with engine.connect() as connection:
            result = connection.execute(
                text("""
                    SELECT
                        current_database() AS database_name,
                        current_user AS username,
                        NOW() AS server_time
                """)
            )

            row = result.mappings().one()

            print("\nCONNEXION REUSSIE !")
            print("-" * 45)
            print("Base :", row["database_name"])
            print("Utilisateur :", row["username"])
            print("Heure serveur :", row["server_time"])

            # 6. Verifier les tables du projet
            result = connection.execute(
                text("""
                    SELECT table_name
                    FROM information_schema.tables
                    WHERE table_schema = 'public'
                      AND table_name IN (
                          'providers',
                          'datasets',
                          'products',
                          'import_runs',
                          'product_price_history',
                          'rejected_rows'
                      )
                    ORDER BY table_name
                """)
            )

            tables = result.scalars().all()

            print("\nTables MyBestSim :")

            if tables:
                for table in tables:
                    print("  [OK]", table)
            else:
                print("  Aucune table trouvee.")
                print("  Execute le schema SQL du projet.")

            print("\nTest termine.")

    except SQLAlchemyError as error:
        print("\nECHEC DE CONNEXION POSTGRESQL")
        print("-" * 45)
        print("Type :", type(error).__name__)
        print("Details :", str(error))
        sys.exit(1)

    except Exception as error:
        print("\nERREUR INATTENDUE")
        print("Type :", type(error).__name__)
        print("Details :", str(error))
        sys.exit(1)

    finally:
        if engine is not None:
            engine.dispose()


if __name__ == "__main__":
    main()
