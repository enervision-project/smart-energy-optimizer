"""Prepare uniquement la base MLflow puis applique ses migrations."""

from contextlib import closing
import os
import subprocess
import sys

import psycopg2
from psycopg2 import sql

from settings import backend_uri, database_settings


def main() -> int:
    settings = database_settings()
    app_database = os.environ["POSTGRES_DB"]
    admin_user = os.environ["POSTGRES_USER"]

    if settings["dbname"] in {app_database, "postgres", "template0", "template1"}:
        raise ValueError("La base MLflow doit etre distincte de la base applicative.")
    if settings["user"] == admin_user:
        raise ValueError("MLflow doit utiliser son propre utilisateur PostgreSQL.")

    # CREATE DATABASE se fait hors transaction ; une relance reutilise l'existant.
    with closing(psycopg2.connect(
        host=settings["host"],
        port=settings["port"],
        dbname="postgres",
        user=admin_user,
        password=os.environ["POSTGRES_PASSWORD"],
        connect_timeout=10,
    )) as connection:
        connection.autocommit = True
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname = %s",
                (settings["dbname"],),
            )
            owner = cursor.fetchone()
            if owner and owner[0] != settings["user"]:
                raise ValueError("La base MLflow existe avec un autre proprietaire.")

            cursor.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (settings["user"],))
            if cursor.fetchone() is None:
                cursor.execute(
                    sql.SQL("CREATE ROLE {} LOGIN PASSWORD %s").format(
                        sql.Identifier(settings["user"])
                    ),
                    (settings["password"],),
                )

            if owner is None:
                cursor.execute(
                    sql.SQL("CREATE DATABASE {} OWNER {}").format(
                        sql.Identifier(settings["dbname"]), sql.Identifier(settings["user"])
                    )
                )

    # Les migrations sont executees avec le compte MLflow, jamais le compte admin.
    print(f"Base MLflow disponible : {settings['dbname']}.")
    return subprocess.run(["mlflow", "db", "upgrade", backend_uri()], check=False).returncode


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, KeyError, psycopg2.Error) as error:
        print(f"Initialisation MLflow impossible : {error}", file=sys.stderr)
        raise SystemExit(1)
