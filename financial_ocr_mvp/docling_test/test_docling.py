from docling.document_converter import DocumentConverter
import json
import os


# =========================
# CONFIG
# =========================

PDF_PATH = "../pdf/FPT_Q1_2015_consolidated_2316c6e5.pdf"

OUTPUT_DIR = "../output/docling"

os.makedirs(
    OUTPUT_DIR,
    exist_ok=True
)


# =========================
# LOAD DOC CONVERTER
# =========================

print("Loading Docling...")

converter = DocumentConverter()


# =========================
# CONVERT PDF
# =========================

print("Processing PDF...")


result = converter.convert(
    PDF_PATH
)


doc = result.document


print("Conversion completed")


# =========================
# EXPORT MARKDOWN
# =========================

markdown = doc.export_to_markdown()


with open(
    f"{OUTPUT_DIR}/FPT_Q1_2015.md",
    "w",
    encoding="utf-8"
) as f:
    f.write(markdown)



# =========================
# EXPORT JSON
# =========================

json_data = doc.export_to_dict()


with open(
    f"{OUTPUT_DIR}/FPT_Q1_2015.json",
    "w",
    encoding="utf-8"
) as f:

    json.dump(
        json_data,
        f,
        ensure_ascii=False,
        indent=2
    )


print("Saved:")
print(
    f"{OUTPUT_DIR}/FPT_Q1_2015.md"
)

print(
    f"{OUTPUT_DIR}/FPT_Q1_2015.json"
)