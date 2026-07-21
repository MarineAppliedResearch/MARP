from pathlib import Path

base = Path(r"datasets")

print("\n=== DATASET FOLDERS FOUND ===")
for d in base.iterdir():
    if d.is_dir():
        print("DATASET:", d)

print("\n=== SPECIES FOLDERS FOUND ===")
for dataset in base.iterdir():
    fr = dataset / "for_human_review"
    if fr.exists():
        for sp in fr.iterdir():
            print("SPECIES:", sp)

print("\n=== SAMPLE FILES FOUND IN EACH SPECIES FOLDER ===")
for dataset in base.iterdir():
    fr = dataset / "for_human_review"
    if fr.exists():
        for sp in fr.iterdir():
            files = list(sp.iterdir())
            print(f"\n{sp}  →  {len(files)} total files")
            for f in files[:10]:
                print("   ", f.name)