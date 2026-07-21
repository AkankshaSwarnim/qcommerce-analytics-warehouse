"""
load_raw.py — land the source files into the warehouse `raw` schema.

WHAT THIS STANDS IN FOR
-----------------------
In a real deployment this step does not exist as a Python script. Fivetran,
Airbyte, or a Datastream CDC job lands each source system into BigQuery on its
own schedule, and dbt picks up from there. This script is that layer, collapsed
to something that runs on a laptop in four seconds.

WHY IT IS A SEPARATE STEP AND NOT PART OF dbt
---------------------------------------------
Because it is a different job with a different owner. dbt transforms data that
is already in the warehouse; it does not extract. Blurring that line is how you
end up with a dbt project that cannot be run by anyone who lacks production
credentials to eight source systems.

The `raw` schema is deliberately dumb: no casting, no renaming, no cleaning. It
is a faithful copy of what the source sent, defects and all. Every repair is
visible in staging/, where it can be read and argued with. A pipeline that
cleans data during ingestion is a pipeline where nobody can answer "what did
the source actually say?"

RUN
    python src/load_raw.py
"""

from pathlib import Path
import duckdb

RAW_DIR = Path("data/raw")
DB_PATH = Path("data/warehouse.duckdb")

# Note _truth_test_accounts.csv is NOT loaded. It is the answer key. Putting it
# in the warehouse would let a model join to it, and the whole point is that the
# warehouse has to find the bots the hard way.
SOURCES = [
    "raw_customers",
    "raw_products",
    "raw_darkstores",
    "raw_order_events",
    "raw_order_items",
    "raw_fulfilment_events",
    "raw_sessions",
    "raw_experiment_assignments",
]


def main() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(DB_PATH))
    con.execute("create schema if not exists raw")

    for name in SOURCES:
        csv = RAW_DIR / f"{name}.csv"
        if not csv.exists():
            raise FileNotFoundError(
                f"{csv} missing. Run `python src/generate_data.py` first."
            )
        con.execute(f"create or replace table raw.{name} as "
                    f"select * from read_csv_auto('{csv.as_posix()}', sample_size=-1)")
        n = con.execute(f"select count(*) from raw.{name}").fetchone()[0]
        print(f"  raw.{name:<32} {n:>10,} rows")

    con.close()
    print(f"\nLanded into {DB_PATH}")


if __name__ == "__main__":
    import os
    os.chdir(Path(__file__).resolve().parents[1])
    print("Landing source systems into the warehouse `raw` schema ...")
    main()
