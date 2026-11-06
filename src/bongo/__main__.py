from bongo.cli import main

# Garde indispensable sous Windows : le rendu en parallèle relance ce module dans chaque processus
if __name__ == "__main__":
    raise SystemExit(main())
