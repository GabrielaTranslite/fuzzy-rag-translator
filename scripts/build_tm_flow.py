import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))  # Add project root to sys.path


from prefect import flow, task
import ingest
import index_qdrant

@task
def ingest_step():
    ingest.main() # Run the ingest.py script to parse .po files and load into the database

@task
def index_step():
    index_qdrant.main() # Run the index_qdrant.py script to create the Qdrant index

@flow(name="build_tm")
def build_tm():
    ingest_step()
    index_step()
    
if __name__ == "__main__":
    build_tm()
