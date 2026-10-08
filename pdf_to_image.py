import fitz
import os


pdf_path = "pdf/FPT_Q1_2015.pdf"

output_dir = "images"

os.makedirs(output_dir, exist_ok=True)


doc = fitz.open(pdf_path)


for page_number in range(len(doc)):

    page = doc[page_number]

    pix = page.get_pixmap(
        dpi=200
    )

    output = f"{output_dir}/page_{page_number+1:03}.png"

    pix.save(output)

    print(
        "saved:",
        output
    )


