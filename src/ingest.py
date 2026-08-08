import polib, json, hashlib
from pathlib import Path
from collections import Counter

PROJECT_ROOT = Path(__file__).resolve().parents[1] 
source_folder = PROJECT_ROOT / "data"
target_folder = PROJECT_ROOT / "data" / "tm"


# Parsing .po files and writing to JSONL
def parse_po_files_to_jsonl(source_folder: Path, target_folder: Path) -> None:
    for po_path in source_folder.glob("*.po"):
        target_path = target_folder / (po_path.stem + ".jsonl")
        # Load the .po file and write its entries to a JSONL file
        po = polib.pofile(str(po_path))
        with target_path.open("w", encoding="utf-8") as f:
            for entry in po.translated_entries():
                if entry.msgid_plural:        # skipping plural entries for now
                    continue
                # Generate a unique ID based on the source file, context, and msgid
                rec_id = hashlib.md5(f"{po_path.stem}|{entry.msgctxt or ''}|{entry.msgid}".encode("utf-8")).hexdigest()
                record = {
                    "id": rec_id,
                    "source_file": po_path.name,
                    "source": entry.msgid,
                    "target": entry.msgstr,
                    "msgctxt": entry.msgctxt,
                    "wml_context": entry.comment,
                    "occurrences": entry.occurrences,
                    "flags": entry.flags
                    }
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        
        print(f"Processed {po_path.name} -> {target_path}")
    
# Join all JSONL files into a single JSONL file


def merge_jsonl_files(target_folder: Path) -> None:
    translation_memory_path = target_folder / "translation_memory.jsonl"
    with translation_memory_path.open("w", encoding="utf-8") as out_f:
        for jsonl_file in target_folder.glob("*.jsonl"):
            if jsonl_file.name == "translation_memory.jsonl":
                continue  # Skip the output file itself
            with jsonl_file.open("r", encoding="utf-8") as in_f:
                for line in in_f:
                    out_f.write(line)
                
    # Verify that all IDs are unique across the merged TM
    ids = [json.loads(l)["id"]
        for l in translation_memory_path.read_text(encoding="utf-8").splitlines()]
    assert len(ids) == len(set(ids)), f"Duplicate ids detected: {len(ids) - len(set(ids))}"


    dupes = [i for i, c in Counter(ids).items() if c > 1]
    if dupes:
        print(f"Duplicate ids: {dupes[:10]}")
    
def main() -> None:
    target_folder.mkdir(parents=True, exist_ok=True)   # create output dir at run time, not import time
    parse_po_files_to_jsonl(source_folder, target_folder)
    merge_jsonl_files(target_folder)


if __name__ == "__main__":
    main()

